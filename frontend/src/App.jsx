import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE_URL?.trim() || "";
const MAX_UPLOAD_BYTES = 24 * 1024 * 1024;
const HEALTH_POLL_MS = 5000;

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function assetUrl(url) {
  if (!url) return "";
  if (/^(https?:|data:|blob:)/i.test(url)) return url;
  return apiUrl(url);
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  );
  const value = bytes / 1024 ** exponent;
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

function isImageFile(file) {
  return (
    file.type.startsWith("image/") ||
    /\.(png|jpe?g|webp|bmp|tiff?)$/i.test(file.name)
  );
}

async function fetchJson(path, options) {
  const response = await fetch(apiUrl(path), options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : null;

  if (!response.ok) {
    throw new Error(
      data?.detail || data?.message || `Request failed (${response.status})`,
    );
  }

  return data;
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () =>
      reject(reader.error || new Error("Could not read the file."));
    reader.readAsDataURL(file);
  });
}

function JsonBlock({ value }) {
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

function modelStateLabel(modelHealth) {
  if (!modelHealth) return "Waiting";
  if (modelHealth.loaded) return "Loaded";
  if (modelHealth.loading) return "Loading";
  if (modelHealth.load_error) return "Failed";
  return "Waiting";
}

function App() {
  const [health, setHealth] = useState(null);
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [analysis, setAnalysis] = useState(null);
  const [history, setHistory] = useState([]);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [historyLoadingId, setHistoryLoadingId] = useState(null);
  const fileInputRef = useRef(null);

  const pipelineReady = Boolean(health?.yolo?.loaded && health?.donut?.loaded);
  const modelLoadError =
    health?.yolo?.load_error || health?.donut?.load_error || "";
  const modelStatus = useMemo(() => {
    if (!health) return "Checking";
    if (pipelineReady) return `Ready · ${health.device}`;
    if (health.yolo?.loading) return `Loading YOLO · ${health.device}`;
    if (health.donut?.loading) return `Loading DONUT · ${health.device}`;
    if (health.yolo?.load_error) return `YOLO failed · ${health.device}`;
    if (health.donut?.load_error) return `DONUT failed · ${health.device}`;
    return `Preparing · ${health.device}`;
  }, [health, pipelineReady]);

  const visibleError = error || connectionError || modelLoadError;
  const sourceImageUrl = useMemo(
    () => assetUrl(analysis?.source_image?.url || analysis?.image_url),
    [analysis],
  );
  const previewSource = previewUrl || sourceImageUrl;
  const groupedRows = Object.entries(analysis?.grouped_predictions || {});
  const activeHistoryId = analysis?.analysis_id;

  const loadMeta = useCallback(async () => {
    try {
      const nextHealth = await fetchJson("/api/health");
      setHealth(nextHealth);
      setConnectionError("");

      try {
        setHistory(await fetchJson("/api/analyses"));
      } catch {
        setHistory([]);
      }

      return Boolean(nextHealth.yolo?.loaded && nextHealth.donut?.loaded);
    } catch {
      setConnectionError("Could not connect to the backend.");
      return false;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    let intervalId;

    async function pollMeta() {
      const ready = await loadMeta();
      if (!cancelled && ready && intervalId) {
        window.clearInterval(intervalId);
      }
    }

    pollMeta();
    intervalId = window.setInterval(pollMeta, HEALTH_POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [loadMeta]);

  useEffect(() => {
    return () => {
      if (previewUrl.startsWith("blob:")) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  const selectFile = useCallback(selected => {
    if (!selected) return;

    if (!isImageFile(selected)) {
      setFile(null);
      setPreviewUrl("");
      setAnalysis(null);
      setError("Please select a valid image file.");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    if (selected.size > MAX_UPLOAD_BYTES) {
      setFile(null);
      setPreviewUrl("");
      setAnalysis(null);
      setError(
        `File is too large. Current limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`,
      );
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    setFile(selected);
    setAnalysis(null);
    setError("");
    setPreviewUrl(URL.createObjectURL(selected));
  }, []);

  async function handleFileChange(event) {
    selectFile(event.target.files?.[0]);
  }

  function resetSelection() {
    setFile(null);
    setPreviewUrl("");
    setAnalysis(null);
    setError("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function runAnalysis() {
    if (!file || !pipelineReady) return;
    setLoading(true);
    setError("");

    try {
      const imagePayload = await readFileAsDataUrl(file);
      const data = await fetchJson("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          image_base64: imagePayload,
        }),
      });

      setAnalysis(data);
      setHistory(await fetchJson("/api/analyses"));
    } catch (err) {
      setError(err.message || "Pipeline error");
    } finally {
      setLoading(false);
    }
  }

  async function loadAnalysisFromHistory(analysisId) {
    setHistoryLoadingId(analysisId);
    setError("");

    try {
      const detail = await fetchJson(`/api/analyses/${analysisId}`);
      setFile(null);
      setPreviewUrl("");
      setAnalysis(detail.payload);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      setError(err.message || "Could not load this history item.");
    } finally {
      setHistoryLoadingId(null);
    }
  }

  return (
    <div className="shell">
      <header className="hero card">
        <div>
          <p className="eyebrow">Mechanical Drawings</p>
          <h1>Local demo for YOLO + DONUT pipeline</h1>
          <p className="lead">
            Upload a drawing, detect regions with YOLO, then parse each crop
            with DONUT. Both models load from Hugging Face inside one backend.
          </p>
        </div>
        <div className="status-stack">
          <div className={`status-chip ${pipelineReady ? "ready" : "pending"}`}>
            <span className="status-dot" />
            {modelStatus}
          </div>
          <p className="status-meta">
            YOLO: {modelStateLabel(health?.yolo)} · DONUT:{" "}
            {modelStateLabel(health?.donut)}
          </p>
        </div>
      </header>

      {visibleError ? (
        <div className="error-box card">{visibleError}</div>
      ) : null}

      <section className="workspace">
        <aside className="panel card">
          <h2>Upload</h2>
          <div
            className="dropzone"
            onClick={() => fileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={event => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileInputRef.current?.click();
              }
            }}
          >
            <div className="dropzone-title">Choose a drawing image</div>
            <div className="dropzone-hint">
              PNG, JPG, WEBP, BMP, TIFF · max {formatBytes(MAX_UPLOAD_BYTES)}
            </div>
            <div className="file-info">
              {file ? (
                <>
                  <span className="file-name" title={file.name}>
                    {file.name}
                  </span>
                  <span className="file-size">{formatBytes(file.size)}</span>
                </>
              ) : (
                <span className="file-name muted">No drawing selected</span>
              )}
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            hidden
            onChange={handleFileChange}
          />
          <div className="actions">
            <button
              type="button"
              className="btn primary"
              onClick={runAnalysis}
              disabled={!file || loading || !pipelineReady}
            >
              {loading ? "Running" : "Run pipeline"}
            </button>
            <button
              type="button"
              className="btn secondary"
              onClick={resetSelection}
              disabled={!file && !analysis && !error}
            >
              Clear
            </button>
          </div>

          <h2>History</h2>
          <div className="history-list">
            {history?.length ? (
              history.map(item => (
                <button
                  type="button"
                  className={`history-item${activeHistoryId === item.id ? " selected" : ""}`}
                  key={item.id}
                  onClick={() => loadAnalysisFromHistory(item.id)}
                  disabled={historyLoadingId === item.id}
                >
                  <span className="history-thumb">
                    {item.image_url ? (
                      <img
                        src={assetUrl(item.image_url)}
                        alt=""
                        loading="lazy"
                      />
                    ) : null}
                  </span>
                  <span className="history-meta">
                    <strong
                      title={item.filename || "no filename"}
                    >
                      #{item.id} · {item.filename || "no filename"}
                    </strong>
                    <span>
                      {item.detection_count} regions ·{" "}
                      {new Date(item.created_at).toLocaleString("en-US")}
                    </span>
                  </span>
                </button>
              ))
            ) : (
              <div className="empty-list">No saved records yet.</div>
            )}
          </div>
        </aside>

        <main className="panel card">
          <div className="card-head">
            <div>
              <h2>{analysis?.filename || file?.name || "Preview"}</h2>
              <p className="subtle">
                Backend: {health?.status || "unknown"} · Storage:{" "}
                {health?.image_storage?.provider || "local"}
              </p>
            </div>
            <div className="badge-row">
              <span className="badge">
                {analysis
                  ? `${analysis.image_size.width} × ${analysis.image_size.height}`
                  : "N/A"}
              </span>
              <span className="badge warn">
                {analysis
                  ? `${analysis.detection_count} detections`
                  : "Waiting"}
              </span>
            </div>
          </div>

          <div className="preview-frame">
            {previewSource ? (
              <img src={previewSource} alt="Preview" />
            ) : (
              <div className="empty-state">
                The drawing preview will appear here.
              </div>
            )}
          </div>

          <div className="results-grid">
            <article className="result-card">
              <div className="card-head">
                <h2>Detections</h2>
                <span>
                  {analysis ? `${analysis.detection_count} regions` : "Not run"}
                </span>
              </div>
              <div className="result-list">
                {analysis?.detections?.length ? (
                  analysis.detections.map(item => (
                    <div
                      className="detection-item"
                      key={`${item.index}-${item.label}`}
                    >
                      <div className="thumb">
                        {item.crop_preview ? (
                          <img
                            src={item.crop_preview}
                            alt="crop preview"
                            loading="lazy"
                          />
                        ) : null}
                      </div>
                      <div className="detection-meta">
                        <div className="badge-row">
                          <span className="badge">#{item.index}</span>
                          <span className="badge warn">
                            {(item.confidence * 100).toFixed(1)}%
                          </span>
                        </div>
                        <strong>{item.label}</strong>
                        <JsonBlock value={item.prediction} />
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="empty-list">No detection data yet.</div>
                )}
              </div>
            </article>

            <article className="result-card">
              <div className="card-head">
                <h2>Output JSON</h2>
                <span>
                  {groupedRows.length
                    ? `${groupedRows.length} groups`
                    : "Empty"}
                </span>
              </div>
              {groupedRows.length ? (
                <div className="result-list">
                  {groupedRows.map(([label, outputs]) => (
                    <div className="json-group-item" key={label}>
                      <div className="detection-meta">
                        <div className="badge-row">
                          <span className="badge">{label}</span>
                          <span className="badge warn">
                            {outputs.length} items
                          </span>
                        </div>
                        <JsonBlock
                          value={outputs.length === 1 ? outputs[0] : outputs}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="empty-list">No output data yet.</div>
              )}
            </article>
          </div>
        </main>
      </section>

      {loading ? (
        <div className="loading-overlay">
          <div className="spinner" />
          <p>Running YOLO and DONUT...</p>
        </div>
      ) : null}
    </div>
  );
}

export default App;
