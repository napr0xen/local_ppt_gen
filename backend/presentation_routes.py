
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse

from presentation_jobs import (
    create_job,
    get_job,
    update_job,
)
from presentation_pipeline import (
    run_presentation_pipeline,
    resolve_template,
    ALLOWED_SOURCE_EXTENSIONS,
    TEMPLATES_DIR,
    GENERATED_DIR,
)


router = APIRouter(
    prefix="/presentations",
    tags=["Presentations"],
)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024


def process_presentation_job(
    job_id,
    source_filename,
    source_content,
    template_name,
    model,
):
    """Execute the pipeline in the background."""

    try:
        update_job(
            job_id,
            status="processing",
            stage="Starting presentation pipeline",
            progress=2,
        )

        def progress_callback(job_id, **changes):
            update_job(job_id, **changes)

        result = run_presentation_pipeline(
            job_id=job_id,
            source_filename=source_filename,
            source_content=source_content,
            template_name=template_name,
            model=model,
            progress_callback=progress_callback,
        )

        update_job(
            job_id,
            status="completed",
            stage="Presentation generated successfully",
            progress=100,
            result=result,
        )

    except Exception as error:
        update_job(
            job_id,
            status="failed",
            stage="Presentation generation failed",
            error=str(error),
        )


@router.get("/templates")
async def list_presentation_templates():
    """List available PowerPoint templates."""

    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

    templates = sorted(
        path.name
        for path in TEMPLATES_DIR.glob("*.pptx")
        if path.is_file()
    )

    return {"templates": templates}


@router.post("/jobs", status_code=202)
async def create_presentation_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    template_name: str = Form(...),
    model: str = Form("qwen3:14b"),
):
    """Upload a source document and start a presentation job."""

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="No source document was selected.",
        )

    source_filename = Path(file.filename).name

    extension = Path(source_filename).suffix.lower()

    if extension not in ALLOWED_SOURCE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Upload a PDF, DOCX or TXT source document.",
        )

    if not template_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Please select a PowerPoint template.",
        )

    if not model.strip():
        raise HTTPException(
            status_code=400,
            detail="Please select an Ollama model.",
        )

    try:
        resolve_template(template_name)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail=str(error),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="The uploaded source document is empty.",
        )

    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail="The maximum upload size is 50 MB.",
        )

    job = create_job(
        source_filename=source_filename,
        template_name=template_name,
        model=model.strip(),
    )

    background_tasks.add_task(
        process_presentation_job,
        job["job_id"],
        source_filename,
        content,
        template_name,
        model.strip(),
    )

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "message": "Presentation generation job created.",
    }


@router.get("/jobs/{job_id}")
async def get_presentation_job(job_id: str):
    """Return the current status and result of a job."""

    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Presentation job not found.",
        )

    return job


@router.get("/jobs/{job_id}/download")
async def download_presentation(job_id: str):
    """Download the generated PowerPoint."""

    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Presentation job not found.",
        )

    if job["status"] != "completed" or not job.get("result"):
        raise HTTPException(
            status_code=409,
            detail="The presentation is not ready for download.",
        )

    output_path = Path(
        job["result"]["output_path"]
    ).resolve()

    generated_dir = GENERATED_DIR.resolve()

    if (
        output_path.parent != generated_dir
        or not output_path.is_file()
        or output_path.suffix.lower() != ".pptx"
    ):
        raise HTTPException(
            status_code=404,
            detail="Generated presentation file not found.",
        )

    return FileResponse(
        path=output_path,
        filename=job["result"]["output_filename"],
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "presentationml.presentation"
        ),
    )
