
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

const API_URL = "http://localhost:8000";

function MarkdownCode({ className, children, ...props }) {
  const [copied, setCopied] = useState(false);
  const isBlock = Boolean(className);
  const code = String(children).replace(/\n$/, "");

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      console.error("Could not copy code.");
    }
  }

  if (!isBlock) {
    return <code {...props}>{children}</code>;
  }

  return (
    <div className="code-block">
      <div className="code-toolbar">
        <span>{className.replace("language-", "") || "Code"}</span>
        <button onClick={copyCode} className="copy-code">
          {copied ? "Copied!" : "Copy code"}
        </button>
      </div>
      <pre>
        <code className={className} {...props}>
          {children}
        </code>
      </pre>
    </div>
  );
}

function App() {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [connection, setConnection] = useState("checking");

  useEffect(() => {
    loadModels();
  }, []);

  async function loadModels() {
    setConnection("checking");
    setError("");

    try {
      const result = await fetch(`${API_URL}/api/models`);

      if (!result.ok) {
        throw new Error("Could not retrieve Ollama models.");
      }

      const data = await result.json();
      setModels(data.models || []);

      setSelectedModel((current) =>
        data.models.includes(current)
          ? current
          : data.models[0] || ""
      );

      setConnection(data.models.length ? "connected" : "empty");

      if (!data.models.length) {
        setError("No models found. Install an Ollama model first.");
      }
    } catch (err) {
      setConnection("offline");
      setError(err.message);
    }
  }

  async function generateResponse() {
    if (!prompt.trim() || !selectedModel || loading) return;

    setLoading(true);
    setError("");
    setResponse("");
    setCopied(false);

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

  async function copyResponse() {
    try {
      await navigator.clipboard.writeText(response);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Unable to copy response.");
    }
  }

  function clearWorkspace() {
    if (loading) return;
    setPrompt("");
    setResponse("");
    setError("");
    setCopied(false);
  }

  return (
    <main className="app">
      <header className="header">
        <div className="brand">
          <div className="brand-icon">AI</div>
          <span>LOCAL AI</span>
        </div>

        <div className="header-right">
          <span className={`connection ${connection}`}>
            <span className="status-dot" />
            {connection === "connected"
              ? "Ollama connected"
              : connection === "checking"
              ? "Checking connection"
              : "Ollama unavailable"}
          </span>
        </div>
      </header>

      <section className="workspace">
        <div className="intro">
          <span className="eyebrow">LOCAL AI WORKSPACE</span>
          <h1>What can I help you with?</h1>
          <p>
            Your AI assistant, powered entirely by locally
            running models.
          </p>
        </div>

        <section className="panel">
          <div className="panel-top">
            <div>
              <label htmlFor="model">AI MODEL</label>
              <p className="field-description">
                Choose an installed Ollama model
              </p>
            </div>

            <button
              className="refresh"
              onClick={loadModels}
              disabled={connection === "checking" || loading}
              title="Refresh available models"
            >
              ↻ Refresh
            </button>
          </div>

          <select
            id="model"
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            disabled={!models.length || loading}
          >
            {models.length === 0 && (
              <option value="">No models available</option>
            )}

            {models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>

          <div className="input-heading">
            <label htmlFor="prompt">YOUR PROMPT</label>
            <span>{prompt.length.toLocaleString()} characters</span>
          </div>

          <textarea
            id="prompt"
            placeholder="Ask anything... e.g. Create a Python palindrome function."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && e.metaKey) {
                generateResponse();
              }
            }}
            disabled={loading}
          />

          <div className="actions">
            <button
              className="clear-button"
              onClick={clearWorkspace}
              disabled={loading || (!prompt && !response)}
            >
              Clear
            </button>

            <button
              className="generate"
              onClick={generateResponse}
              disabled={loading || !prompt.trim() || !selectedModel}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  Generating...
                </>
              ) : (
                <>
                  Generate response <span>→</span>
                </>
              )}
            </button>
          </div>

          <div className="keyboard-hint">
            Press <kbd>⌘</kbd> + <kbd>Enter</kbd> to generate
          </div>

          {error && <div className="error">{error}</div>}
        </section>

        {(response || loading) && (
          <section className="panel output">
            <div className="output-header">
              <div>
                <span className="eyebrow">GENERATED OUTPUT</span>
                <h2>Response</h2>
              </div>

              {response && (
                <button className="copy-response" onClick={copyResponse}>
                  {copied ? "✓ Copied" : "Copy response"}
                </button>
              )}
            </div>

            {loading ? (
              <div className="loading-state">
                <span className="spinner" />
                <p>Waiting for your local AI model...</p>
                <span>This may take a moment.</span>
              </div>
            ) : (
              <article className="response-text">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{ code: MarkdownCode }}
                >
                  {response}
                </ReactMarkdown>
              </article>
            )}

            {response && (
              <div className="output-footer">
                Generated with {selectedModel}
              </div>
            )}
          </section>
        )}

        <footer className="footer">
          <span>LOCAL AI GENERATOR</span>
          <span>Powered by Ollama</span>
        </footer>
      </section>
    </main>
  );
}

export default App;
