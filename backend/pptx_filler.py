
from pathlib import Path
from datetime import datetime
import re

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


TARGET_ID_PATTERN = re.compile(
    r"^slide_(\d+)_(shape_\d+(?:_\d+)*)$"
)

UNRESOLVED_PLACEHOLDER_PATTERN = re.compile(
    r"\[[^\]]+\]"
)


def build_element_index(elements):
    """Index template elements, including nested group children."""
    index = {}

    for element in elements:
        index[element["id"]] = element

        children = element.get("children", [])
        index.update(build_element_index(children))

    return index


def locate_shape(slide, shape_path):
    """
    Resolve shape_12 or shape_2_1 using the same
    one-based numbering used by template_inspector.py.
    """
    parts = shape_path.replace("shape_", "").split("_")

    try:
        shape = slide.shapes[int(parts[0]) - 1]
    except (IndexError, ValueError):
        raise ValueError(f"Shape not found: {shape_path}")

    for part in parts[1:]:
        if shape.shape_type != MSO_SHAPE_TYPE.GROUP:
            raise ValueError(
                f"{shape_path} contains a child path "
                "but its parent is not a group."
            )

        try:
            shape = shape.shapes[int(part) - 1]
        except (IndexError, ValueError):
            raise ValueError(f"Grouped shape not found: {shape_path}")

    return shape


def find_token_runs(shape, token):
    """
    Find runs containing the complete placeholder token.

    Tokens split across multiple runs are rejected to avoid
    damaging PowerPoint formatting.
    """
    matches = []

    for paragraph in shape.text_frame.paragraphs:
        for run in paragraph.runs:
            if token in run.text:
                matches.append(run)

    return matches


def prepare_mappings(mappings, element_index, presentation):
    """
    Validate every destination before making any edits.

    Multiple placeholders in the same shape are allowed,
    but the same placeholder cannot be mapped twice.
    """
    prepared = []
    used_placeholders = set()

    for mapping in mappings:

        if not isinstance(mapping, dict):
            raise ValueError("Each mapping must be a dictionary.")

        target_id = mapping.get("target_id")
        operation = mapping.get("operation")
        content = mapping.get("content")
        token = mapping.get("placeholder_token")

        if not isinstance(target_id, str):
            raise ValueError("Mapping has an invalid target ID.")

        match = TARGET_ID_PATTERN.fullmatch(target_id)

        if not match:
            raise ValueError(f"Invalid target ID: {target_id}")

        slide_number = int(match.group(1))
        shape_path = match.group(2)

        if not 1 <= slide_number <= len(presentation.slides):
            raise ValueError(f"Invalid slide number: {target_id}")

        if operation != "replace_text":
            raise ValueError(
                f"Unsupported operation for {target_id}: {operation}"
            )

        if not isinstance(content, str) or not content.strip():
            raise ValueError(
                f"Invalid replacement content: {target_id}"
            )

        content = content.strip()

        if UNRESOLVED_PLACEHOLDER_PATTERN.search(content):
            raise ValueError(
                f"Replacement contains an unresolved placeholder: "
                f"{target_id}"
            )

        if not isinstance(token, str) or not token:
            raise ValueError(
                f"Invalid placeholder token for {target_id}"
            )

        # Identify a specific placeholder, not just its shape.
        placeholder_key = (target_id, token)

        if placeholder_key in used_placeholders:
            raise ValueError(
                f"Duplicate placeholder mapping: {target_id} | {token}"
            )

        element = element_index.get(target_id)

        if not element:
            raise ValueError(
                f"Target not found in template structure: {target_id}"
            )

        if (
            element.get("type") != "text"
            or element.get("mappable") is not True
            or element.get("protected_candidate") is True
        ):
            raise ValueError(
                f"Target is not an eligible text placeholder: {target_id}"
            )

        if token not in element.get("placeholder_tokens", []):
            raise ValueError(
                f"Token was not approved for {target_id}: {token}"
            )

        slide = presentation.slides[slide_number - 1]
        shape = locate_shape(slide, shape_path)

        if (
            not shape.has_text_frame
            or shape.has_table
            or shape.has_chart
            or shape.shape_type == MSO_SHAPE_TYPE.GROUP
        ):
            raise ValueError(
                f"Live PowerPoint shape is not editable text: {target_id}"
            )

        runs = find_token_runs(shape, token)

        if not runs:
            raise ValueError(
                f"Placeholder not found in a single text run: "
                f"{target_id} | {token}"
            )

        prepared.append({
            "target_id": target_id,
            "shape": shape,
            "token": token,
            "content": content,
            "runs": runs,
        })

        used_placeholders.add(placeholder_key)

    return prepared


def fill_powerpoint(
    template_path,
    template_structure,
    validated_mappings,
    output_path=None,
):
    """
    Create a separate PowerPoint copy and replace
    approved text placeholders only.
    """
    template_path = Path(template_path).resolve()

    if not template_path.exists():
        raise FileNotFoundError(
            f"Template not found: {template_path}"
        )

    if template_structure.get("template_name") != template_path.name:
        raise ValueError(
            "Template structure does not match the selected "
            "PowerPoint template."
        )

    presentation = Presentation(template_path)

    if len(presentation.slides) != template_structure.get("slide_count"):
        raise ValueError(
            "Slide count does not match the inspected template."
        )

    element_index = build_element_index(
        template_structure.get("elements", [])
    )

    # Validate every mapping before modifying the presentation.
    prepared = prepare_mappings(
        validated_mappings,
        element_index,
        presentation,
    )

    if output_path is None:
        output_dir = template_path.parent.parent / "generated"
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        output_path = (
            output_dir
            / f"{template_path.stem}_filled_{timestamp}.pptx"
        )
    else:
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path == template_path:
        raise ValueError(
            "Output path cannot be the original template."
        )

    # All validation has passed. Now make the replacements.
    replacement_count = 0

    for item in prepared:
        for run in item["runs"]:
            occurrences = run.text.count(item["token"])

            if occurrences:
                run.text = run.text.replace(
                    item["token"],
                    item["content"],
                )

                replacement_count += occurrences

    presentation.save(output_path)

    return {
        "output_path": str(output_path),
        "replacement_count": replacement_count,
        "mapping_count": len(validated_mappings),
    }
