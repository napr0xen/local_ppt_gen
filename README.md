# Local AI Generator API

A lightweight REST API built using **FastAPI** that connects a frontend application to locally hosted AI models through **Ollama**.

The API allows users to retrieve available Ollama models and generate AI responses to be used on powerpoint by submitting documents and selecting a model and a template through a frontend interface.

## Features

- **Model Retrieval:** Fetches the list of locally available Ollama models.
- **Text Generation:** Accepts user prompts and generates responses using the selected model.
- **Frontend Integration:** Supports cross-origin requests from a local frontend application using CORS.
- **Asynchronous Requests:** Uses `httpx.AsyncClient` for non-blocking HTTP communication with Ollama.
- **Error Handling:** Handles connection failures, invalid inputs, and Ollama API errors.


## Prerequisites

Ensure the following are installed:

1. Python 3.10 or later
2. Ollama
3. At least one Ollama model downloaded locally
4. Node.js and npm (for the frontend)


### 3. Install Dependencies

Create a `requirements.txt` file:

```text
fastapi
uvicorn
httpx
pydantic
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

### 4. Start the Backend Server

Navigate to the backend directory and run:

```bash
uvicorn main:app --reload
```

The backend will be available at:

```text
http://localhost:8000
```

Interactive API documentation:

```text
http://localhost:8000/docs
```

## Application Workflow

1. The frontend sends a GET request to `/api/models`.
2. The backend communicates with Ollama and retrieves installed models.
3. The frontend displays the available models.
4. The user enters a prompt and selects a model.
5. The frontend sends a POST request to `/api/generate`.
6. FastAPI validates the request and forwards it to Ollama.
7. Ollama generates the response.
8. The backend returns the generated text to the frontend.


```text
http://localhost:8000/docs
```

Alternatively, use cURL:

**Retrieve Models:**

```bash
curl http://localhost:8000/api/models
```

**Generate Response:**

```bash
curl -X POST http://localhost:8000/api/generate \
-H "Content-Type: application/json" \
-d "{\"prompt\":\"Hello, how are you?\",\"model\":\"llama3.2\"}"
```
