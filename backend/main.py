
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="Local AI Generator API")

OLLAMA_URL = "http://localhost:11434"

SYSTEM_INSTRUCTION = """
You are a precise, concise assistant.

STRICT RESPONSE RULES:

1. Answer exactly what the user requests.
2. Never add unnecessary introductions or conclusions.
3. Never say "Here is", "Sure", or "Certainly".
4. If the user requests a function or code without asking
   for an explanation, output ONLY the code.
5. Do not include explanations, comments, examples, or
   documentation unless explicitly requested.
6. If the user requests a specific format, follow it exactly.
7. Keep normal explanations as short as possible.
8. Do not repeat the user's question.
9. Do not add information that was not requested.
10. Prioritize correctness over verbosity.

CODE OUTPUT:
- Return executable code.
- For code-only requests, use a Markdown fenced code block
  with no surrounding explanation.
- The rendered answer must contain only the requested code.
- Do not add explanatory text before or after the code.
- Include only necessary code comments.

Your objective is to produce the shortest complete answer
that satisfies the user's request.
"""

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    prompt: str
    model: str


@app.get("/")
async def root():
    return {
        "status": "running",
        "application": "Local AI Generator"
    }


@app.get("/api/models")
async def get_models():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{OLLAMA_URL}/api/tags"
            )
            response.raise_for_status()
            data = response.json()

        return {
            "models": [
                model["name"]
                for model in data.get("models", [])
            ]
        }

    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Cannot connect to Ollama. Make sure Ollama is running."
        )


@app.post("/api/generate")
async def generate(request: GenerateRequest):

    if not request.prompt.strip():
        raise HTTPException(
            status_code=400,
            detail="Please enter some text."
        )

    if not request.model.strip():
        raise HTTPException(
            status_code=400,
            detail="Please select a model."
        )

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": request.model,
                    "system": SYSTEM_INSTRUCTION,
                    "prompt": request.prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2
                    }
                }
            )

            response.raise_for_status()
            data = response.json()

        return {
            "response": data.get("response", "").strip(),
            "model": request.model
        }

    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama returned an error: {error.response.text}"
        )

    except httpx.HTTPError:
        raise HTTPException(
            status_code=503,
            detail="Unable to communicate with Ollama."
        )
