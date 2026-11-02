
import json
import re
import unicodedata
import math


# --------------------------------------------------
# TEXT NORMALIZATION
# --------------------------------------------------

def normalize_text(value):
    """Normalize harmless text-extraction differences."""

    if not isinstance(value, str):
        return ""

    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\u00a0", " ")
    value = value.replace("\u2018", "'").replace("\u2019", "'")
    value = value.replace("\u201c", '"').replace("\u201d", '"')
    value = re.sub(r"\s+", " ", value)

    return value.strip()


# --------------------------------------------------
# SLIDE CONTEXT
# --------------------------------------------------

def get_slide_number(element_id):
    """Extract slide number from IDs such as slide_4_shape_6."""

    match = re.match(r"slide_(\d+)_shape_", str(element_id))

    if not match:
        return None

    return int(match.group(1))


def build_slide_context(element, all_elements):
    """Collect readable text from the same slide."""

    slide_number = get_slide_number(element.get("id"))

    if slide_number is None:
        return []

    slide_elements = [
        item
        for item in all_elements
        if get_slide_number(item.get("id")) == slide_number
        and item.get("type") == "text"
        and isinstance(item.get("text"), str)
        and item.get("text").strip()
    ]

    slide_elements.sort(
        key=lambda item: (
            item.get("position", {}).get("y", 0),
            item.get("position", {}).get("x", 0)
        )
    )

    return [
        {
            "element_id": item.get("id"),
            "text": item.get("text", "").strip(),
            "is_current_target": item.get("id") == element.get("id")
        }
        for item in slide_elements
    ]


# --------------------------------------------------
# BUILD INDIVIDUAL PLACEHOLDER TARGETS
# --------------------------------------------------

def build_eligible_targets(template_structure):
    """Create one independent target for every placeholder."""

    elements = template_structure.get("elements", [])

    all_elements = template_structure.get(
        "context_elements",
        elements
    )

    eligible_targets = []

    for element in elements:

        if not (
            element.get("type") == "text"
            and element.get("mappable") is True
            and element.get("placeholder_tokens")
        ):
            continue

        tokens = element.get("placeholder_tokens", [])

        slide_context = build_slide_context(
            element,
            all_elements
        )

        for index, token in enumerate(tokens):

            eligible_targets.append({
                "target_id": element["id"],
                "placeholder_token": token,
                "element_text": element.get("text", ""),
                "slide_number": get_slide_number(element.get("id")),
                "placeholder_position": index + 1,
                "placeholders_in_same_element": tokens,
                "slide_context": slide_context
            })

    return eligible_targets


# --------------------------------------------------
# SOURCE RETRIEVAL
# --------------------------------------------------

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this",
    "these", "those", "was", "were", "are", "is", "has",
    "have", "had", "not", "but", "can", "could", "should",
    "would", "will", "into", "than", "then", "their",
    "there", "they", "them", "its", "our", "you", "your",
    "what", "when", "where", "which", "who", "how",
    "about", "also", "only", "each", "per", "all",
    "any", "some", "such", "more", "most", "other",
    "use", "using", "used", "information", "content",
    "insight", "opportunity", "placeholder"
}


def tokenize(text):
    """Extract useful search terms."""

    words = re.findall(
        r"[A-Za-z0-9][A-Za-z0-9.%/-]*",
        str(text).lower()
    )

    return [
        word for word in words
        if word not in STOPWORDS and len(word) > 2
    ]


def split_source_into_chunks(source_text, max_chunk_size=1800):
    """
    Split source text into passages.

    Original wording is preserved. Paragraphs are kept intact
    whenever possible.
    """

    if not isinstance(source_text, str) or not source_text.strip():
        return []

    paragraphs = re.split(r"\n\s*\n", source_text.strip())

    chunks = []

    for paragraph in paragraphs:

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        if len(paragraph) <= max_chunk_size:
            chunks.append(paragraph)
            continue

        # Split oversized paragraphs into overlapping passages.
        step = max_chunk_size - 200

        for start in range(0, len(paragraph), step):

            chunk = paragraph[start:start + max_chunk_size].strip()

            if chunk:
                chunks.append(chunk)

    return chunks


def retrieve_relevant_passages(
    source_text,
    eligible_targets,
    max_chunks=14,
    max_characters=12000
):
    """
    Retrieve source passages relevant to the current slide.

    This function selects source passages only.
    Qwen makes all placeholder-mapping decisions.
    """

    chunks = split_source_into_chunks(source_text)

    if not chunks:
        return ""

    query_parts = []

    for target in eligible_targets:

        query_parts.append(target.get("element_text", ""))
        query_parts.append(target.get("placeholder_token", ""))

        for context in target.get("slide_context", []):
            query_parts.append(context.get("text", ""))

    query_terms = set(tokenize(" ".join(query_parts)))

    if not query_terms:
        return "\n\n".join(chunks[:3])[:max_characters]

    document_frequency = {}
    chunk_terms = []

    for chunk in chunks:

        terms = tokenize(chunk)
        term_counts = {}

        for term in terms:
            term_counts[term] = term_counts.get(term, 0) + 1

        chunk_terms.append(term_counts)

        for term in set(terms):
            document_frequency[term] = (
                document_frequency.get(term, 0) + 1
            )

    total_chunks = len(chunks)
    scored_chunks = []

    for index, term_counts in enumerate(chunk_terms):

        score = 0.0

        for term in query_terms:

            frequency = term_counts.get(term, 0)

            if frequency:

                frequency_in_documents = document_frequency.get(term, 0)

                inverse_frequency = (
                    1.0 + math.log(
                        (total_chunks + 1) /
                        (frequency_in_documents + 1)
                    )
                )

                score += min(frequency, 4) * inverse_frequency

        if score > 0:
            scored_chunks.append((score, index))

    if scored_chunks:

        scored_chunks.sort(
            key=lambda item: item[0],
            reverse=True
        )

        selected_indexes = [
            index
            for _, index in scored_chunks[:max_chunks]
        ]

    else:
        selected_indexes = list(range(min(3, len(chunks))))

    selected_indexes.sort()

    selected_passages = []
    total_characters = 0

    for index in selected_indexes:

        passage = chunks[index]

        if total_characters + len(passage) > max_characters:
            remaining = max_characters - total_characters

            if remaining >= 200:
                selected_passages.append(passage[:remaining])

            break

        selected_passages.append(passage)
        total_characters += len(passage)

    return "\n\n".join(
        f"[Retrieved passage {index + 1}]\n{passage}"
        for index, passage in enumerate(selected_passages)
    )


# --------------------------------------------------
# BUILD MAPPING PROMPT
# --------------------------------------------------

def build_mapping_prompt(source_text, template_structure):
    """
    Build a dynamic Qwen mapping prompt.

    Only relevant source passages are supplied to Qwen.
    """

    eligible_targets = build_eligible_targets(
        template_structure
    )

    targets_json = json.dumps(
        eligible_targets,
        indent=2,
        ensure_ascii=False
    )

    retrieved_source = retrieve_relevant_passages(
        source_text,
        eligible_targets
    )

    return f"""
You are a precise document-to-PowerPoint mapping engine.

Your task is to identify information in a source document and
map it to the correct existing placeholders in a PowerPoint template.

You are NOT creating a new presentation.

Accuracy is more important than filling every placeholder.

==================================================
RULE 1 - EXACT DESTINATION
==================================================

Every target is provided separately.

For each mapping:

- Copy target_id exactly.
- Copy placeholder_token exactly.
- Never invent a target ID.
- Never use a placeholder belonging to another target.
- Never combine different targets.
- Map each target_id and placeholder_token combination at most once.

Use all target information to understand the destination.

==================================================
RULE 2 - UNDERSTAND THE SLIDE
==================================================

Understand the purpose of the slide before mapping content.

Use the slide title, headings and surrounding text to identify
the subject of each section.

A placeholder must receive information appropriate to its
specific section.

A supplier-performance insight must not be assigned to a
spend-distribution placeholder unless the destination explicitly
requests it.

A savings observation must not be assigned to a supplier-risk
placeholder.

An opportunity must not be invented from an ordinary observation.

Use the source document as the only authority for factual content.

==================================================
RULE 3 - SOURCE ACCURACY
==================================================

Use ONLY information explicitly present in the supplied
source passages.

Never invent or assume:

- Names or job titles
- Dates or reporting periods
- Financial figures or percentages
- Currency or units
- Contract values or durations
- Supplier names
- Performance results
- Reasons or explanations
- Targets, scoring methods or thresholds
- Actions, owners or deadlines

Do not use general knowledge.
Do not calculate new figures.
Do not derive unsupported conclusions.

==================================================
RULE 4 - EXACT SOURCE EVIDENCE
==================================================

Every source_evidence value must be copied from a supplied
source passage.

Evidence must be a continuous quotation.

Do not:

- Add labels absent from the source.
- Add explanatory words.
- Combine separate sentences.
- Rewrite the source.
- Use ellipses.
- Invent a sentence summarizing the source.

Use the shortest continuous quotation that fully supports
the replacement content.

Retrieved passage labels are reference labels only.
Never include those labels in source_evidence or content.

==================================================
RULE 5 - CONTENT ACCURACY
==================================================

The content must be an exact continuous excerpt from
source_evidence.

Content may be shorter than source_evidence.

Content must never contain:

- Paraphrased information
- Additional explanations
- New calculations
- Unsupported context
- Unresolved square-bracket placeholders

Preserve complete figures and units when the placeholder requests
a complete financial value.

==================================================
RULE 6 - SEMANTIC RELEVANCE
==================================================

Before creating a mapping, ask:

1. What is the slide about?
2. What section does this placeholder belong to?
3. What information does this placeholder request?
4. Does the source evidence directly support that information?
5. Is the information relevant to this exact destination?

A valid source quotation is NOT automatically a valid mapping.

If the information does not clearly belong in the destination,
leave the target unmapped.

==================================================
RULE 7 - MULTIPLE PLACEHOLDERS
==================================================

Treat every placeholder as an independent target.

Do not:

- Return one combined mapping for several placeholders.
- Reuse the same information in several placeholders.
- Assign content based only on placeholder position.
- Assume every placeholder must be filled.

Only map information that directly supports each individual
placeholder.

==================================================
RULE 8 - COVERAGE
==================================================

Review every eligible target independently.

Populate every target for which the supplied source passages
provide supporting information.

If a target has no supporting information, do not create a mapping.

Do not force information into unrelated placeholders.

==================================================
SOURCE DOCUMENT PASSAGES
==================================================

These passages were retrieved from the original source document.

They may be relevant to the current slide, but you must decide
which information is actually suitable for each target.

They are not the complete source document.

If the supplied passages do not support a target, leave it unmapped.
Do not guess what may exist elsewhere in the document.

{retrieved_source}

==================================================
ELIGIBLE PLACEHOLDER TARGETS
==================================================

{targets_json}

==================================================
REQUIRED OUTPUT
==================================================

Return valid JSON only.

Use exactly this structure:

{{
  "mappings": [
    {{
      "target_id": "exact_target_id",
      "placeholder_token": "[exact placeholder]",
      "operation": "replace_text",
      "content": "exact excerpt from source",
      "source_evidence": "continuous exact source quotation",
      "confidence": 0.95
    }}
  ],
  "unmapped_information": [
    "Description of information requested but not provided"
  ]
}}

Additional requirements:

- Only use operation "replace_text".
- Confidence must be a number between 0 and 1.
- Do not include Markdown.
- Do not include explanations outside the JSON.
- Do not create mappings with missing evidence.
- Do not invent content to increase mapping coverage.

==================================================
FINAL CHECK
==================================================

For every mapping, verify:

1. Does the target ID exist?
2. Does the placeholder belong to that exact target?
3. Is the evidence copied from the supplied source passages?
4. Is the content an exact excerpt of its supporting evidence?
5. Does the content directly answer the placeholder?
6. Does the content belong in this slide section?
7. Have you avoided adding unsupported information?

If any check fails, remove that mapping.

Return valid JSON only.
"""


# --------------------------------------------------
# VALIDATE MAPPING PLAN
# --------------------------------------------------

def validate_mapping_plan(mapping_plan, template_structure, source_text):
    """
    Validate AI-generated mappings against the ORIGINAL source document.
    """

    elements = template_structure.get("elements", [])

    available_targets = {
        element["id"]: element
        for element in elements
        if (
            element.get("type") == "text"
            and element.get("mappable") is True
            and element.get("placeholder_tokens")
        )
    }

    validated = []
    rejected = []
    seen_placeholders = set()

    normalized_source = normalize_text(source_text)

    if not isinstance(mapping_plan, dict):
        return {
            "validated_mappings": [],
            "rejected_mappings": [{
                "mapping": mapping_plan,
                "reason": "Mapping plan must be a JSON object."
            }],
            "unmapped_information": []
        }

    mappings = mapping_plan.get("mappings", [])

    if not isinstance(mappings, list):
        return {
            "validated_mappings": [],
            "rejected_mappings": [{
                "mapping": mappings,
                "reason": "Mappings must be a list."
            }],
            "unmapped_information": []
        }

    unmapped_information = mapping_plan.get(
        "unmapped_information",
        []
    )

    if not isinstance(unmapped_information, list):
        unmapped_information = []

    for mapping in mappings:

        if not isinstance(mapping, dict):
            rejected.append({
                "mapping": mapping,
                "reason": "Mapping must be a JSON object."
            })
            continue

        target_id = mapping.get("target_id")
        placeholder_token = mapping.get("placeholder_token")
        operation = mapping.get("operation")
        content = mapping.get("content")
        evidence = mapping.get("source_evidence")
        confidence = mapping.get("confidence")

        if (
            not isinstance(target_id, str)
            or target_id not in available_targets
        ):
            rejected.append({
                "mapping": mapping,
                "reason": "Destination is not an eligible text placeholder."
            })
            continue

        target_element = available_targets[target_id]

        if (
            not isinstance(placeholder_token, str)
            or placeholder_token not in target_element.get(
                "placeholder_tokens", []
            )
        ):
            rejected.append({
                "mapping": mapping,
                "reason": "Placeholder token does not belong to this destination."
            })
            continue

        placeholder_key = (target_id, placeholder_token)

        if placeholder_key in seen_placeholders:
            rejected.append({
                "mapping": mapping,
                "reason": "Duplicate mapping for the same placeholder."
            })
            continue

        if operation != "replace_text":
            rejected.append({
                "mapping": mapping,
                "reason": "Only replace_text is currently allowed."
            })
            continue

        if not isinstance(content, str) or not content.strip():
            rejected.append({
                "mapping": mapping,
                "reason": "Content must be a non-empty string."
            })
            continue

        content = content.strip()

        if re.search(r"\[[^\]]+\]", content):
            rejected.append({
                "mapping": mapping,
                "reason": "Replacement content contains an unresolved placeholder."
            })
            continue

        if not isinstance(evidence, str) or not evidence.strip():
            rejected.append({
                "mapping": mapping,
                "reason": "Source evidence is missing."
            })
            continue

        normalized_evidence = normalize_text(evidence)
        normalized_content = normalize_text(content)

        if normalized_evidence not in normalized_source:
            rejected.append({
                "mapping": mapping,
                "reason": "Evidence was not found in the normalized source document."
            })
            continue

        if normalized_content not in normalized_evidence:
            rejected.append({
                "mapping": mapping,
                "reason": "Replacement content is not an exact excerpt of its supporting evidence."
            })
            continue

        if (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            rejected.append({
                "mapping": mapping,
                "reason": "Invalid confidence score."
            })
            continue

        validated.append({
            **mapping,
            "target_id": target_id,
            "placeholder_token": placeholder_token,
            "content": content,
            "source_evidence": evidence.strip(),
            "confidence": float(confidence)
        })

        seen_placeholders.add(placeholder_key)

    return {
        "validated_mappings": validated,
        "rejected_mappings": rejected,
        "unmapped_information": unmapped_information
    }


# --------------------------------------------------
# PARSE OLLAMA RESPONSE
# --------------------------------------------------

def parse_mapping_response(model_response):
    """Parse the JSON structure returned by Ollama."""

    try:
        result = json.loads(model_response)

        if not isinstance(result, dict):
            raise ValueError("Response must be a JSON object.")

        if not isinstance(result.get("mappings"), list):
            raise ValueError("Missing or invalid mappings list.")

        if not isinstance(result.get("unmapped_information", []), list):
            raise ValueError("Invalid unmapped_information list.")

        return result

    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(
            f"Could not parse mapping response: {error}"
        ) from error
