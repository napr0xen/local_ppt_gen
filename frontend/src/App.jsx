
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./App.css";

const API_URL = "http://localhost:8000";

function isPresentationRequest(message) {
  return /\b(powerpoint|power point|pptx|ppt|presentation|presentations|slides|slide deck|slide presentation)\b/i.test(
    message
  );
}

function App() {
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const [prompt, setPrompt] = useState("");
  const [file, setFile] = useState(null);
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [connection, setConnection] = useState("checking");
  const [lastMessage, setLastMessage] = useState("");
  const [lastFile, setLastFile] = useState(null);

  const [templates, setTemplates] = useState([]);
  const [templateName, setTemplateName] = useState("");
  const [templatesError, setTemplatesError] = useState("");

  const [jobProgress, setJobProgress] = useState(0);
  const [jobStage, setJobStage] = useState("");
  const [downloadUrl, setDownloadUrl] = useState("");

  const fileInput = useRef(null);
  const bottomRef = useRef(null);

  const presentationMode =
    Boolean(file) && isPresentationRequest(prompt);

  useEffect(() => {
    loadModels();
    loadTemplates();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [response, loading, jobStage]);

  async function loadModels() {
    try {
      const res = await fetch(`${API_URL}/api/models`);

      if (!res.ok) throw new Error("Could not load models.");

      const data = await res.json();
      const available = data.models || [];

      setModels(available);

      setModel((current) =>
        available.includes(current) ? current : available[0] || ""
      );

      setConnection("connected");
    } catch {
      setConnection("offline");
    }
  }

  async function loadTemplates() {
    try {
      setTemplatesError("");

      const res = await fetch(`${API_URL}/presentations/templates`);

      if (!res.ok) {
        throw new Error("Could not load PowerPoint templates.");
      }

      const data = await res.json();
      const available = data.templates || [];

      setTemplates(available);

      setTemplateName((current) =>
        available.includes(current) ? current : available[0] || ""
      );
    } catch (err) {
      setTemplatesError(err.message);
    }
  }

  function attachFile(selected) {
    if (!selected) return;

    const extension = selected.name.split(".").pop().toLowerCase();

    if (!["pdf", "docx", "txt"].includes(extension)) {
      setError("Please upload a PDF, DOCX or TXT file.");
      return;
    }

    if (selected.size > 50 * 1024 * 1024) {
      setError("The maximum upload size is 50 MB.");
      return;
    }

    setFile(selected);
    setError("");
    setResponse("");
    setDownloadUrl("");
  }

  function clearAttachment() {
    setFile(null);

    if (fileInput.current) {
      fileInput.current.value = "";
    }
  }

  async function pollPresentationJob(jobId) {
    while (true) {
      const res = await fetch(
        `${API_URL}/presentations/jobs/${jobId}`
      );

      const job = await res.json();

      if (!res.ok) {
        throw new Error(job.detail || "Could not check presentation status.");
      }

      setJobProgress(job.progress || 0);
      setJobStage(job.stage || "Processing presentation");

      if (job.status === "completed") {
        setDownloadUrl(
          `${API_URL}/presentations/jobs/${jobId}/download`
        );

        const result = job.result || {};

        setResponse(
          [
            "## Your PowerPoint is ready!",
            "",
            `**File:** ${result.output_filename || "Generated presentation.pptx"}`,
            "",
            `**Slides processed:** ${result.slides_processed?.length ?? "N/A"}`,
            `**Accepted mappings:** ${result.accepted_mapping_count ?? 0}`,
            `**Rejected mappings:** ${result.rejected_mapping_count ?? 0}`,
            "",
            "Your generated presentation is ready to download below.",
          ].join("\n")
        );

        setJobProgress(100);
        setJobStage("Presentation generated successfully");

        return;
      }

      if (job.status === "failed") {
        throw new Error(
          job.error || "Presentation generation failed."
        );
      }

      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
  }

  async function generatePresentation() {
    if (!file) {
      throw new Error("Please attach a source document.");
    }

    if (!templateName) {
      throw new Error("Please select a PowerPoint template.");
    }

    if (!model) {
      throw new Error("Please select an Ollama model.");
    }

    setJobProgress(0);
    setJobStage("Uploading your document");

    const formData = new FormData();

    formData.append("file", file);
    formData.append("template_name", templateName);
    formData.append("model", model);

    const res = await fetch(`${API_URL}/presentations/jobs`, {
      method: "POST",
      body: formData,
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(
        data.detail || "Could not start presentation generation."
      );
    }

    setJobStage("Presentation job created");
    setJobProgress(2);

    await pollPresentationJob(data.job_id);
  }

  async function submitMessage() {
    if ((!prompt.trim() && !file) || loading || !model) return;

    const submittedPrompt = prompt.trim();
    const submittedFile = file;
    const shouldGeneratePresentation =
      Boolean(submittedFile) &&
      isPresentationRequest(submittedPrompt);

    setLoading(true);
    setError("");
    setResponse("");
    setDownloadUrl("");
    setLastMessage(submittedPrompt);
    setLastFile(submittedFile);

    try {
      if (shouldGeneratePresentation) {
        await generatePresentation();
      } else {
        setJobStage("");
        setJobProgress(0);

        let res;

        if (submittedFile) {
          const formData = new FormData();

          formData.append("file", submittedFile);
          formData.append("model", model);

          res = await fetch(`${API_URL}/api/summarize`, {
            method: "POST",
            body: formData,
          });
        } else {
          res = await fetch(`${API_URL}/api/generate`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              prompt: submittedPrompt,
              model,
            }),
          });
        }

        const data = await res.json();

        if (!res.ok) {
          throw new Error(data.detail || "Something went wrong.");
        }

        setResponse(
          submittedFile ? data.summary : data.response
        );
      }

      setPrompt("");
      clearAttachment();

    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submitMessage();
    }
  }

  async function copyResponse() {
    try {
      await navigator.clipboard.writeText(response);
    } catch {
      setError("Unable to copy response.");
    }
  }

  return (
    <main className="chat-app">

      {/* HEADER */}

      <header className="chat-header">
        <div className="brand">
          <div className="brand-icon">AI</div>
          <strong>LOCAL AI</strong>
        </div>

        <div className={`connection ${connection}`}>
          <span className="status-dot" />

          {connection === "connected"
            ? "Ollama connected"
            : connection === "checking"
            ? "Connecting..."
            : "Ollama offline"}
        </div>

        <button className="refresh" onClick={loadModels}>
          ↻
        </button>
      </header>

      {/* CHAT AREA */}

      <section className="chat-content">

        {!response && !loading && (
          <div className="welcome">
            <div className="welcome-icon">✦</div>

            <h1>What can I help you with?</h1>

            <p>
              Your AI assistant, powered by locally running models.
            </p>
          </div>
        )}

        {(response || loading || lastMessage) && (
          <div className="conversation">

            <div className="user-message">
              {lastFile && (
                <div className="message-file">
                  <span>▤</span>
                  {lastFile.name}
                </div>
              )}

              {lastMessage}
            </div>

            {loading ? (
              <div className="assistant-message">

                <div className="loading-indicator">
                  <span className="spinner" />

                  <span>
                    {jobStage ||
                      (lastFile
                        ? "Analysing your document..."
                        : "Generating response...")}
                  </span>
                </div>

                {jobStage && (
                  <div className="job-progress">
                    <div className="job-progress-track">
                      <div
                        className="job-progress-fill"
                        style={{ width: `${jobProgress}%` }}
                      />
                    </div>

                    <div className="job-progress-label">
                      <span>{jobStage}</span>
                      <span>{jobProgress}%</span>
                    </div>
                  </div>
                )}

              </div>
            ) : (
              <div className="assistant-message">

                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {response}
                </ReactMarkdown>

                {downloadUrl && (
                  <a
                    className="presentation-download"
                    href={downloadUrl}
                    download
                  >
                    ↓ Download PowerPoint
                  </a>
                )}

                <button
                  className="copy-response"
                  onClick={copyResponse}
                >
                  Copy response
                </button>

              </div>
            )}

            <div ref={bottomRef} />
          </div>
        )}

      </section>

      {/* COMPOSER */}

      <section className="composer-container">

        {file && (
          <div className="attachment-preview">

            <span className="attachment-icon">▤</span>

            <div className="attachment-details">
              <strong>{file.name}</strong>

              <small>
                {(file.size / 1024).toFixed(1)} KB
              </small>
            </div>

            <button
              onClick={clearAttachment}
              disabled={loading}
            >
              ✕
            </button>

          </div>
        )}

        {presentationMode && (
          <div className="template-selector">

            <label htmlFor="template-select">
              PowerPoint template
            </label>

            <select
              id="template-select"
              value={templateName}
              onChange={(e) => setTemplateName(e.target.value)}
              disabled={loading}
            >
              {templates.length === 0 && (
                <option value="">
                  No templates available
                </option>
              )}

              {templates.map((template) => (
                <option key={template} value={template}>
                  {template}
                </option>
              ))}
            </select>

            {templatesError && (
              <small className="template-error">
                {templatesError}
              </small>
            )}

          </div>
        )}

        <div className="composer">

          <textarea
            placeholder="Message your local AI..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            disabled={loading}
          />

          <div className="composer-toolbar">

            <div className="composer-left">

              <button
                className="attach-button"
                onClick={() => fileInput.current?.click()}
                disabled={loading}
                title="Attach document"
              >
                +
              </button>

              <input
                ref={fileInput}
                type="file"
                accept=".pdf,.docx,.txt"
                hidden
                onChange={(e) => attachFile(e.target.files[0])}
              />

              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={loading}
              >
                {models.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>

            </div>

            <button
              className="send-button"
              onClick={submitMessage}
              disabled={
                loading ||
                (!prompt.trim() && !file) ||
                !model ||
                (presentationMode && (
                  !templateName || templates.length === 0
                ))
              }
              title="Send message"
            >
              ↑
            </button>

          </div>
        </div>

        {error && <div className="error">{error}</div>}

        <p className="composer-hint">
          PDF, DOCX and TXT supported · Enter to send · Shift + Enter for a new line
        </p>

      </section>

      <footer className="chat-footer">
        Powered by Ollama · Runs locally
      </footer>

    </main>
  );
}

export default App;
