
import re
import json
import time
import requests

from pathlib import Path
from io import BytesIO

from pypdf import PdfReader
from docx import Document

from template_inspector import inspect_template
from mapping_engine import (
    build_mapping_prompt,
    parse_mapping_response,
    validate_mapping_plan,
)
from pptx_filler import fill_powerpoint


OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3:14b"

BACKEND_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BACKEND_DIR / "templates"
UPLOADS_DIR = BACKEND_DIR / "uploads" / "presentation_jobs"
GENERATED_DIR = BACKEND_DIR / "generated"

ALLOWED_SOURCE_EXTENSIONS = {".pdf", ".docx", ".txt"}


# --------------------------------------------------
# DOCUMENT EXTRACTION
# --------------------------------------------------

def extract_source_text(filename, content):
    """Extract readable text from PDF, DOCX or TXT files."""

    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_SOURCE_EXTENSIONS:
        raise ValueError(
            "Unsupported source format. Upload PDF, DOCX or TXT."
        )

    if not content:
        raise ValueError("The uploaded source document is empty.")

    if extension == ".pdf":

        reader = PdfReader(BytesIO(content))

        pages = [
            page.extract_text() or ""
            for page in reader.pages
        ]

        text = "\n".join(pages)

    elif extension == ".docx":

        document = Document(BytesIO(content))

        paragraphs = [
            paragraph.text
            for paragraph in document.paragraphs
            if paragraph.text.strip()
        ]

        for table in document.tables:

            for row in table.rows:

                paragraphs.append(
                    " | ".join(cell.text for cell in row.cells)
                )

        text = "\n".join(paragraphs)

    else:

        try:
            text = content.decode("utf-8-sig")

        except UnicodeDecodeError:
            text = content.decode("utf-8", errors="replace")

    if not text.strip():
        raise ValueError(
            "No readable text was found. "
            "Scanned PDFs may require OCR."
        )

    return text


# --------------------------------------------------
# FILE MANAGEMENT
# --------------------------------------------------

def save_uploaded_source(job_id, filename, content):
    """Save an uploaded source under a job-specific filename."""

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    safe_filename = Path(filename).name
    extension = Path(safe_filename).suffix.lower()

    if extension not in ALLOWED_SOURCE_EXTENSIONS:
        raise ValueError("Unsupported source document format.")

    source_path = UPLOADS_DIR / f"{job_id}_{safe_filename}"

    source_path.write_bytes(content)

    return source_path


def resolve_template(template_name):
    """Resolve a template safely inside the templates directory."""

    safe_name = Path(template_name).name

    if safe_name != template_name:
        raise ValueError("Invalid template filename.")

    if Path(safe_name).suffix.lower() != ".pptx":
        raise ValueError("The selected template must be a PPTX file.")

    template_path = (TEMPLATES_DIR / safe_name).resolve()

    if template_path.parent != TEMPLATES_DIR.resolve():
        raise ValueError("Invalid template location.")

    if not template_path.is_file():
        raise FileNotFoundError(
            f"Template not found: {safe_name}"
        )

    return template_path


# --------------------------------------------------
# TEMPLATE HELPERS
# --------------------------------------------------

def get_slide_number(element_id):
    """Read the slide number from an inspector element ID."""

    match = re.match(r"^slide_(\d+)_", element_id or "")

    if not match:
        return None

    return int(match.group(1))


def get_eligible_slides(template_structure):
    """Find slides containing eligible text placeholders."""

    slides = set()

    for element in template_structure.get("elements", []):

        if (
            element.get("type") == "text"
            and element.get("mappable") is True
            and element.get("placeholder_tokens")
        ):

            slide_number = get_slide_number(element.get("id"))

            if slide_number is not None:
                slides.add(slide_number)

    return sorted(slides)


# --------------------------------------------------
# QWEN MAPPING
# --------------------------------------------------

def generate_slide_mapping(
    source_text,
    full_template_structure,
    slide_number,
    model,
):
    """
    Generate and validate mappings for one slide using Ollama.

    Qwen makes mapping decisions dynamically.
    Python retrieves passages and validates the output.
    """

    all_elements = full_template_structure.get("elements", [])

    slide_elements = [
        element
        for element in all_elements
        if get_slide_number(element.get("id")) == slide_number
    ]

    slide_structure = {
        **full_template_structure,
        "elements": slide_elements,
        "context_elements": all_elements,
    }

    prompt = build_mapping_prompt(
        source_text,
        slide_structure,
    )

    print(
        f"[Mapping] Slide {slide_number}: "
        f"Original source = {len(source_text):,} characters | "
        f"Qwen prompt = {len(prompt):,} characters"
    )

    started_at = time.perf_counter()

    model_response_parts = []
    stream_completed = False
    metrics = {}

    try:

        with requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": True,
                "think": True,
                "format": "json",
                "keep_alive": "30m",
                "options": {
                    "temperature": 0,
                    "num_ctx": 32768,
                },
            },
            stream=True,
            timeout=(10, None),
        ) as response:

            response.raise_for_status()

            for line in response.iter_lines(decode_unicode=True):

                if not line:
                    continue

                try:
                    chunk = json.loads(line)

                except ValueError as error:
                    raise RuntimeError(
                        f"Invalid streaming JSON from Ollama "
                        f"for slide {slide_number}."
                    ) from error

                if chunk.get("error"):
                    raise RuntimeError(
                        f"Ollama error on slide {slide_number}: "
                        f"{chunk['error']}"
                    )

                response_piece = chunk.get("response")

                if isinstance(response_piece, str) and response_piece:
                    model_response_parts.append(response_piece)

                if chunk.get("done") is True:

                    stream_completed = True

                    metrics = {
                        "total_duration": chunk.get("total_duration"),
                        "load_duration": chunk.get("load_duration"),
                        "prompt_eval_count": chunk.get("prompt_eval_count"),
                        "prompt_eval_duration": chunk.get(
                            "prompt_eval_duration"
                        ),
                        "eval_count": chunk.get("eval_count"),
                        "eval_duration": chunk.get("eval_duration"),
                    }

                    break

    except requests.exceptions.ConnectionError as error:

        raise RuntimeError(
            "Cannot connect to Ollama. "
            "Check that Ollama is running."
        ) from error

    except requests.exceptions.Timeout as error:

        raise RuntimeError(
            f"Connection to Ollama timed out for slide {slide_number}."
        ) from error

    except requests.exceptions.HTTPError as error:

        raise RuntimeError(
            f"Ollama returned an HTTP error: {error}"
        ) from error

    except requests.exceptions.RequestException as error:

        raise RuntimeError(
            f"Ollama streaming failed on slide {slide_number}: {error}"
        ) from error

    elapsed_seconds = time.perf_counter() - started_at

    print(
        f"[Ollama] Slide {slide_number} finished in "
        f"{elapsed_seconds:.2f}s"
    )

    if metrics:

        print(
            f"[Ollama] Slide {slide_number} metrics: "
            f"{json.dumps(metrics)}"
        )

    if not stream_completed:

        raise RuntimeError(
            f"Ollama stream ended before completion for "
            f"slide {slide_number}. No mapping was validated."
        )

    model_response = "".join(model_response_parts)

    if not model_response.strip():

        raise RuntimeError(
            f"Ollama returned an empty response for slide {slide_number}."
        )

    try:

        mapping_plan = parse_mapping_response(model_response)

    except ValueError as error:

        raise RuntimeError(
            f"Could not parse the mapping response for "
            f"slide {slide_number}: {error}"
        ) from error

    validation_result = validate_mapping_plan(
        mapping_plan,
        slide_structure,
        source_text,
    )

    print(
        f"[Mapping] Slide {slide_number}: "
        f"{len(validation_result['validated_mappings'])} accepted | "
        f"{len(validation_result['rejected_mappings'])} rejected"
    )

    return validation_result


# --------------------------------------------------
# COMPLETE PRESENTATION PIPELINE
# --------------------------------------------------

def run_presentation_pipeline(
    job_id,
    source_filename,
    source_content,
    template_name,
    model=DEFAULT_MODEL,
    progress_callback=None,
):
    """Run the complete presentation-generation workflow."""

    def report(progress, stage):

        if progress_callback:

            progress_callback(
                job_id,
                progress=progress,
                stage=stage,
                status="processing",
            )

    if not model or not model.strip():
        raise ValueError("An Ollama model must be selected.")

    model = model.strip()

    report(5, "Saving uploaded document")

    source_path = save_uploaded_source(
        job_id,
        source_filename,
        source_content,
    )

    report(10, "Extracting document text")

    source_text = extract_source_text(
        source_filename,
        source_content,
    )

    report(20, "Inspecting PowerPoint template")

    template_path = resolve_template(template_name)

    template_structure = inspect_template(template_path)

    slide_count = template_structure["slide_count"]

    eligible_slides = get_eligible_slides(template_structure)

    eligible_placeholder_count = sum(
        len(element.get("placeholder_tokens", []))
        for element in template_structure.get("elements", [])
        if (
            element.get("type") == "text"
            and element.get("mappable") is True
        )
    )

    if not eligible_slides:

        raise ValueError(
            "The selected template contains no eligible text placeholders."
        )

    report(25, "Preparing slide-by-slide mapping")

    all_validated = []
    all_rejected = []
    all_unmapped = []

    total_slides_to_process = len(eligible_slides)

    for index, slide_number in enumerate(eligible_slides, start=1):

        stage = (
            f"Mapping slide {slide_number} "
            f"({index} of {total_slides_to_process})"
        )

        progress = 25 + int(
            (index - 1) / total_slides_to_process * 55
        )

        report(progress, stage)

        result = generate_slide_mapping(
            source_text=source_text,
            full_template_structure=template_structure,
            slide_number=slide_number,
            model=model,
        )

        all_validated.extend(
            result["validated_mappings"]
        )

        all_rejected.extend(
            result["rejected_mappings"]
        )

        all_unmapped.extend(
            result["unmapped_information"]
        )

        completed_progress = 25 + int(
            index / total_slides_to_process * 55
        )

        report(
            completed_progress,
            f"Completed slide {slide_number} "
            f"({index} of {total_slides_to_process})"
        )

    report(85, "Preparing PowerPoint output")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    output_path = (
        GENERATED_DIR
        / f"{job_id}_{template_path.stem}_filled.pptx"
    )

    fill_result = fill_powerpoint(
        template_path=template_path,
        template_structure=template_structure,
        validated_mappings=all_validated,
        output_path=output_path,
    )

    report(95, "Checking generated PowerPoint")

    if not output_path.is_file() or output_path.stat().st_size == 0:

        raise RuntimeError(
            "PowerPoint generation did not produce a valid output file."
        )

    return {
        "source_filename": Path(source_filename).name,
        "source_path": str(source_path),
        "template_name": template_path.name,
        "model": model,
        "source_characters": len(source_text),
        "slide_count": slide_count,
        "slides_processed": eligible_slides,
        "eligible_placeholder_count": eligible_placeholder_count,
        "accepted_mapping_count": len(all_validated),
        "rejected_mapping_count": len(all_rejected),
        "unmapped_information_count": len(all_unmapped),
        "replacement_count": fill_result["replacement_count"],
        "validated_mappings": all_validated,
        "rejected_mappings": all_rejected,
        "unmapped_information": all_unmapped,
        "output_filename": output_path.name,
        "output_path": str(output_path),
    }
