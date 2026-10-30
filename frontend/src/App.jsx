import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";;

const API_URL = "http://localhost:8000";

function App() {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadModels();
  }, []);

  async function loadModels() {
    try {
      setError("");

      const result = await fetch(`${API_URL}/api/models`);

      if (!result.ok) {
        throw new Error("Could not connect to Ollama.");
      }

      const data = await result.json();

      setModels(data.models || []);

      if (data.models?.length > 0) {
        setSelectedModel(data.models[0]);
      } else {
        setError("No Ollama models found. Install a model first.");
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function generateResponse() {
    if (!prompt.trim() || !selectedModel) return;

    setLoading(true);
    setError("");
    setResponse("");

    try {
      const result = await fetch(`${API_URL}/api/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt,
          model: selectedModel,
        }),
      });

      const data = await result.json();

      if (!result.ok) {
        throw new Error(data.detail || "Generation failed.");
      }

      setResponse(data.response);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="app">
      <header className="header">
        <div className="logo">LOCAL AI</div>
        <span className="status">Local environment</span>
      </header>

      <section className="workspace">
        <div className="intro">
          <h1>AI Workspace</h1>
          <p>
            Enter your text and let your local AI model
            process it.
          </p>
        </div>

        <div className="panel">
          <label>Select AI Model</label>

          <div className="model-row">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
            >
              {models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>

            <button
              className="refresh"
              onClick={loadModels}
              disabled={loading}
            >
              Refresh
            </button>
          </div>

          <label htmlFor="prompt">Your Input</label>

          <textarea
            id="prompt"
            placeholder="Enter your text or instructions here..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />

          <button
            className="generate"
            onClick={generateResponse}
            disabled={loading || !prompt.trim() || !selectedModel}
          >
            {loading ? "Processing..." : "Generate Response"}
          </button>

          {error && (
            <div className="error">{error}</div>
          )}
        </div>

        {(response || loading) && (
          <div className="panel output">
            <h2>AI Response</h2>

            {loading ? (
              <p>Waiting for Ollama...</p>
            ) : (
              <div className="response-text">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {response}
              </ReactMarkdown>
            </div>
            )}
          </div>
        )}
      </section>
    </main>
  );
}

export default App;
