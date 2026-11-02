
import requests

from mapping_engine import (
    build_mapping_prompt,
    parse_mapping_response,
    validate_mapping_plan,
)


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:14b"
TIMEOUT = 300


def generate_mapping(source_text, template_structure):
    """
    Send source information and eligible PowerPoint placeholders
    to Ollama, parse its response and validate every mapping.

    Returns:
        validated_mappings
        rejected_mappings
        unmapped_information
    """

    if not isinstance(source_text, str) or not source_text.strip():
        raise ValueError("Source document text is empty.")

    if not isinstance(template_structure, dict):
        raise ValueError("Template structure must be a dictionary.")

    prompt = build_mapping_prompt(
        source_text,
        template_structure,
    )
    print("\n========== INPUT DIAGNOSTICS ==========")
    print("Source characters:", len(source_text))
    print("Source preview:")
    print(source_text[:1000])

    eligible_count = sum(
        1 for element in template_structure.get("elements", [])
        if (
            element.get("type") == "text"
            and element.get("mappable") is True
            and element.get("placeholder_tokens")
        )
    )

    print("\nEligible template elements:", eligible_count)
    print("Prompt characters:", len(prompt))
    print("Prompt contains source:", source_text[:200] in prompt)
    print("=======================================\n")
    print(f"Sending source information to {MODEL}...")

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0,
                },
            },
            timeout=TIMEOUT,
        )

        response.raise_for_status()

    except requests.exceptions.ConnectionError as error:
        raise RuntimeError(
            "Could not connect to Ollama. "
            "Check that Ollama is running."
        ) from error

    except requests.exceptions.Timeout as error:
        raise RuntimeError(
            f"Ollama did not respond within {TIMEOUT} seconds."
        ) from error

    except requests.exceptions.HTTPError as error:
        raise RuntimeError(
            f"Ollama returned an HTTP error: {error}"
        ) from error

    try:
        response_data = response.json()
    except ValueError as error:
        raise RuntimeError(
            "Ollama returned an invalid HTTP response."
        ) from error

    model_response = response_data.get("response")

    if not isinstance(model_response, str) or not model_response.strip():
        raise RuntimeError(
            "Ollama returned an empty model response."
        )

    try:
        mapping_plan = parse_mapping_response(model_response)
        print("\n========== RAW OLLAMA RESPONSE ==========")
        print(model_response)
        print("========== END RAW RESPONSE ==========\n")
    except ValueError as error:
        raise RuntimeError(
            f"Could not parse Ollama's mapping response: {error}"
        ) from error

    validation_result = validate_mapping_plan(
        mapping_plan,
        template_structure,
        source_text,
    )

    print("Mapping response validated.")
    print(
        f"Accepted: {len(validation_result['validated_mappings'])}"
    )
    print(
        f"Rejected: {len(validation_result['rejected_mappings'])}"
    )

    return {
        "validated_mappings": validation_result["validated_mappings"],
        "rejected_mappings": validation_result["rejected_mappings"],
        "unmapped_information": validation_result["unmapped_information"],
    }
