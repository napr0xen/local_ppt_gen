
from pathlib import Path
import json
import re
import sys

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


PROTECTED_TERMS = [
    "classification:",
    "confidential",
    "company logo",
]

PLACEHOLDER_PATTERN = re.compile(r"\[[^\]]+\]")


def get_shape_type(shape):
    if shape.has_table:
        return "table"
    if shape.has_chart:
        return "chart"
    if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
        return "image"
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        return "group"
    if shape.has_text_frame:
        return "text"
    return "shape"


def inspect_shape(shape, slide_number, shape_path):
    shape_type = get_shape_type(shape)
    element_id = f"slide_{slide_number}_{shape_path}"

    text = ""
    if shape.has_text_frame:
        text = shape.text.strip()

    is_placeholder = bool(
        shape.is_placeholder
        if hasattr(shape, "is_placeholder")
        else False
    )

    tokens = PLACEHOLDER_PATTERN.findall(text)

    protected = any(
        term in text.lower()
        for term in PROTECTED_TERMS
    )

    element = {
        "id": element_id,
        "name": shape.name,
        "type": shape_type,
        "position": {
            "x": round(shape.left / 914400, 3),
            "y": round(shape.top / 914400, 3),
            "width": round(shape.width / 914400, 3),
            "height": round(shape.height / 914400, 3),
        },
        "text": text,
        "is_placeholder": is_placeholder,
        "placeholder_tokens": tokens,
        "protected_candidate": protected,

        # Only explicit, unprotected text placeholders
        # are eligible for automatic text mapping.
        "mappable": (
            shape_type == "text"
            and bool(tokens)
            and not protected
        ),
    }

    # Tables are inspected but not yet eligible
    # for automatic mapping.
    if shape.has_table:
        table = shape.table

        cells = [
            [cell.text.strip() for cell in row.cells]
            for row in table.rows
        ]

        element["table"] = {
            "rows": len(table.rows),
            "columns": len(table.columns),
            "cells": cells,
        }

        element["mappable"] = False
        element["requires_review"] = not protected
        element["mapping_method"] = "structured_table_mapping"

    # Charts are inspected but not yet eligible
    # for automatic mapping.
    elif shape.has_chart:
        chart = shape.chart

        element["chart"] = {
            "chart_type": str(chart.chart_type),
            "series": [
                {
                    "name": series.name,
                    "values": list(series.values),
                }
                for series in chart.series
            ],
        }

        element["mappable"] = False
        element["requires_review"] = not protected
        element["mapping_method"] = "structured_chart_mapping"

    # Recursively inspect grouped shapes.
    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
        element["children"] = []

        for child_number, child in enumerate(
            shape.shapes, start=1
        ):
            child_element = inspect_shape(
                child,
                slide_number,
                f"{shape_path}_{child_number}",
            )

            element["children"].append(child_element)

    return element


def inspect_template(template_path):
    path = Path(template_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Template not found: {path.resolve()}"
        )

    presentation = Presentation(path)

    result = {
        "template_name": path.name,
        "slide_count": len(presentation.slides),
        "dimensions_inches": {
            "width": round(
                presentation.slide_width / 914400, 3
            ),
            "height": round(
                presentation.slide_height / 914400, 3
            ),
        },
        "slides": [],
        "elements": [],
    }

    for slide_number, slide in enumerate(
        presentation.slides, start=1
    ):
        slide_data = {
            "slide_number": slide_number,
            "elements": [],
        }

        for shape_number, shape in enumerate(
            slide.shapes, start=1
        ):
            element = inspect_shape(
                shape,
                slide_number,
                f"shape_{shape_number}",
            )

            slide_data["elements"].append(element)
            result["elements"].append(element)

        result["slides"].append(slide_data)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python template_inspector.py "
            "templates/your_template.pptx"
        )
        sys.exit(1)

    template_path = sys.argv[1]

    structure = inspect_template(template_path)

    output_path = Path("template_structure.json")

    output_path.write_text(
        json.dumps(
            structure,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("Template inspection complete.")
    print(f"Slides detected: {structure['slide_count']}")
    print(f"Elements detected: {len(structure['elements'])}")
    print(f"JSON report: {output_path.resolve()}")
