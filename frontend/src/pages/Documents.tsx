import { useState } from "react";
import type { FormEvent } from "react";
import { documentsApi, errMsg } from "../lib/api";
import type { DocumentSummary } from "../lib/types";
import { Badge, Empty, ErrorBox, FilePicker, fmtBytes, Modal, PageHead, SuccessBox, TableSkeleton, useAsync } from "../components/ui";

function typeForFile(f: File | null): string {
  if (!f) return "pdf";
  const ext = (f.name.split(".").pop() || "").toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "md" || ext === "markdown") return "markdown";
  if (ext === "doc" || ext === "docx") return "docx";
  if (ext === "html" || ext === "htm") return "html";
  if (ext === "xlsx") return "xlsx";
  if (ext === "xls") return "xls";
  if (ext === "txt" || ext === "json" || ext === "csv") return "text";
  return "other";
}

const CLASSIFICATIONS = [
  { value: "public", label: "public", tone: "green" as const, info: "Visible to everyone in the tenant. Non-sensitive material such as syllabus, brochures." },
  { value: "internal", label: "internal", tone: "blue" as const, info: "For internal use only. Default choice for everyday course and company material." },
  { value: "confidential", label: "confidential", tone: "amber" as const, info: "Sensitive — access is limited to specific users or roles. Explicit grants required." },
  { value: "restricted", label: "restricted", tone: "red" as const, info: "Highest sensitivity — exams, keys, salaries. Only explicitly granted users can access." },
];

export default function Documents() {
  const { data: docs, loading, error: loadError, reload } = useAsync<DocumentSummary[]>(() => documentsApi.list(), []);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [classification, setClassification] = useState("internal");

  const [replaceId, setReplaceId] = useState<string | null>(null);
  const [replaceFile, setReplaceFile] = useState<File | null>(null);

  const doUpload = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      await documentsApi.upload(file, title || file.name, typeForFile(file), classification);
      setSuccess(`Uploaded "${file.name}"`);
      setUploadOpen(false);
      setFile(null);
      setTitle("");
      reload();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (id: string) => {
    if (!confirm("Delete this document and its chunks?")) return;
    try {
      await documentsApi.delete(id);
      reload();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const doReindex = async (id: string) => {
    try {
      await documentsApi.reindex(id);
      reload();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const doReplace = async () => {
    if (!replaceId || !replaceFile) return;
    setBusy(true);
    setError("");
    try {
      await documentsApi.replace(replaceId, replaceFile);
      setSuccess("Document replaced and re-ingested");
      setReplaceId(null);
      setReplaceFile(null);
      reload();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHead title="Documents" sub="Upload, replace, re-index and delete tenant documents.">
        <button className="btn primary" onClick={() => setUploadOpen(true)}>
          + Upload
        </button>
      </PageHead>
      <ErrorBox msg={error || loadError} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="card">
        {loading && <TableSkeleton rows={5} cols={6} />}
        {!loading && (!docs || docs.length === 0) && <Empty>No documents yet.</Empty>}
        {docs && docs.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Type</th>
                <th>Classification</th>
                <th>Size</th>
                <th>Chunks</th>
                <th>Version</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id}>
                  <td>
                    <div>{d.title}</div>
                    <div className="mono muted">{d.filename}</div>
                  </td>
                  <td>{d.document_type}</td>
                  <td>
                    <Badge tone={d.classification === "public" ? "green" : d.classification === "restricted" ? "red" : "blue"}>
                      {d.classification}
                    </Badge>
                  </td>
                  <td>{fmtBytes(d.size_bytes)}</td>
                  <td>{d.chunk_count}</td>
                  <td>v{d.version}</td>
                  <td>
                    <Badge tone={d.status === "READY" ? "green" : d.status === "FAILED" ? "red" : "amber"}>
                      {d.status}
                    </Badge>
                  </td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button className="btn sm" onClick={() => setReplaceId(d.id)}>
                        Replace
                      </button>
                      <button className="btn sm" onClick={() => doReindex(d.id)}>
                        Reindex
                      </button>
                      <button className="btn sm danger" onClick={() => doDelete(d.id)}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {uploadOpen && (
        <Modal title="Upload document" onClose={() => setUploadOpen(false)}>
          <form onSubmit={doUpload}>
            <div className="field">
              <label>File</label>
              <FilePicker file={file} onChange={setFile} />
            </div>
            <div className="field">
              <label>Title (optional)</label>
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Defaults to filename" />
            </div>
            <div className="grid cols-2">
              <div className="field">
                <label>Type</label>
                <div className="type-detected" aria-hidden>
                  <Badge tone="blue">{file ? typeForFile(file) : "—"}</Badge>
                  <span className="muted">detected from file</span>
                </div>
              </div>
              <div className="field">
                <label>Classification</label>
                <select value={classification} onChange={(e) => setClassification(e.target.value)}>
                  {CLASSIFICATIONS.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {(() => {
              const meta = CLASSIFICATIONS.find((c) => c.value === classification);
              return meta ? (
                <div className="classification-hint">
                  <Badge tone={meta.tone}>{meta.label}</Badge>
                  <span>{meta.info}</span>
                </div>
              ) : null;
            })()}
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setUploadOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || !file}>
                {busy ? "Uploading…" : "Upload"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {replaceId && (
        <Modal title="Replace document file" onClose={() => setReplaceId(null)}>
          <p className="muted">Replaces the stored file and re-ingests it, keeping the document id, title and ACLs.</p>
          <div className="field">
            <label>New file</label>
            <FilePicker file={replaceFile} onChange={setReplaceFile} />
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={() => setReplaceId(null)}>
              Cancel
            </button>
            <button className="btn primary" onClick={doReplace} disabled={busy || !replaceFile}>
              {busy ? "Replacing…" : "Replace & re-ingest"}
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
