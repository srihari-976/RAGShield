import { useState } from "react";
import type { FormEvent } from "react";
import { errMsg, evaluationApi } from "../lib/api";
import { Badge, Empty, ErrorBox, Modal, PageHead, Skeleton, SuccessBox, useAsync } from "../components/ui";

interface GoldenRow {
  id: string;
  question: string;
  expected_document_ids: string[];
  category: string | null;
}

interface RunRow {
  id: string;
  name: string;
  rag_version: string;
  prompt_version: string;
  status: string;
  metrics: Record<string, unknown> | null;
  created_at: string;
}

interface RunItem {
  id: string;
  question: string;
  answer: string | null;
  retrieved_document_ids: string[];
  expected_document_ids: string[];
  recall_at_k: number | null;
  precision_at_k: number | null;
  mrr: number | null;
  ndcg: number | null;
  groundedness: number | null;
  completeness: number | null;
  relevance: number | null;
  latency_ms: number | null;
}

function fmtMetric(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return Number(v).toFixed(3);
}

export default function Evaluation() {
  const { data: golden, loading: gLoading, reload: reloadGolden } = useAsync<GoldenRow[]>(() => evaluationApi.golden(), []);
  const { data: runs, loading: rLoading, reload: reloadRuns } = useAsync<RunRow[]>(() => evaluationApi.runs(), []);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  const [goldenOpen, setGoldenOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [expectedDocs, setExpectedDocs] = useState("");
  const [category, setCategory] = useState("");

  const [runOpen, setRunOpen] = useState(false);
  const [runName, setRunName] = useState("");
  const [ragVersion, setRagVersion] = useState("v1");

  const [selectedRun, setSelectedRun] = useState<RunRow | null>(null);
  const [items, setItems] = useState<RunItem[] | null>(null);
  const [gate, setGate] = useState<Record<string, unknown> | null>(null);
  const [itemsLoading, setItemsLoading] = useState(false);

  const createGolden = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const docIds = expectedDocs.split(",").map((s) => s.trim()).filter(Boolean);
      await evaluationApi.createGolden({ question, expected_document_ids: docIds, category: category || undefined });
      setSuccess("Golden question added");
      setGoldenOpen(false);
      setQuestion("");
      setExpectedDocs("");
      setCategory("");
      reloadGolden();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const startRun = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const run = await evaluationApi.run({ name: runName, rag_version: ragVersion });
      setSuccess(`Evaluation run started (${run.id.slice(0, 8)}). Check back for results.`);
      setRunOpen(false);
      setRunName("");
      reloadRuns();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const inspectRun = async (run: RunRow) => {
    setSelectedRun(run);
    setItems(null);
    setGate(null);
    setItemsLoading(true);
    try {
      const [it, gt] = await Promise.all([
        evaluationApi.runItems(run.id),
        evaluationApi.gate(run.id),
      ]);
      setItems(it.data);
      setGate(gt.data);
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setItemsLoading(false);
    }
  };

  const deleteGolden = async (id: string) => {
    if (!confirm("Delete this golden question?")) return;
    try {
      await evaluationApi.deleteGolden(id);
      reloadGolden();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const metricsOf = (r: RunRow) => r.metrics ?? {};
  const passed = gate ? Boolean((gate as { passed: boolean }).passed) : null;

  return (
    <div>
      <PageHead
        title="Evaluation"
        sub="Golden questions, offline runs (Recall@K / Precision@K / MRR / nDCG), LLM-judge quality and gate checks."
      >
        <div className="row">
          <button className="btn primary" onClick={() => setRunOpen(true)} disabled={!golden || golden.length === 0}>
            ▶ Run evaluation
          </button>
          <button className="btn" onClick={() => setGoldenOpen(true)}>
            + Golden question
          </button>
        </div>
      </PageHead>
      <ErrorBox msg={error} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="grid cols-2">
        <div className="card">
          <h3>Golden questions ({golden?.length ?? 0})</h3>
          {gLoading && (
            <div>
              <Skeleton height={16} />
              <Skeleton height={16} width="70%" />
            </div>
          )}
          {!gLoading && (!golden || golden.length === 0) && <Empty>Add golden questions to run evaluations.</Empty>}
          {golden?.map((q) => (
            <div key={q.id} className="row-between" style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
              <div>
                <div>{q.question}</div>
                {q.category && <div className="muted" style={{ fontSize: 12 }}>{q.category}</div>}
              </div>
              <button className="btn sm danger" onClick={() => deleteGolden(q.id)}>
                Delete
              </button>
            </div>
          ))}
        </div>

        <div className="card">
          <h3>Runs</h3>
          {rLoading && (
            <div>
              <Skeleton height={18} />
              <Skeleton height={18} width="80%" />
              <Skeleton height={18} width="60%" />
            </div>
          )}
          {!rLoading && (!runs || runs.length === 0) && <Empty>No runs yet.</Empty>}
          {runs?.map((r) => {
            const m = metricsOf(r);
            return (
              <div
                key={r.id}
                className="card"
                style={{ marginBottom: 10, cursor: "pointer" }}
                onClick={() => inspectRun(r)}
              >
                <div className="row-between">
                  <strong>{r.name}</strong>
                  <Badge tone={r.status === "COMPLETED" ? "green" : r.status === "RUNNING" ? "amber" : r.status === "FAILED" ? "red" : "blue"}>
                    {r.status}
                  </Badge>
                </div>
                <div className="muted mt" style={{ fontSize: 12 }}>
                  rag {r.rag_version} · prompt {r.prompt_version} · {new Date(r.created_at).toLocaleString()}
                </div>
                {r.status === "COMPLETED" && m && (
                  <div className="mono mt" style={{ fontSize: 12 }}>
                    recall@5 {fmtMetric(m.recall_at_5)} · precision@5 {fmtMetric(m.precision_at_5)} · mrr {fmtMetric(m.mrr)} · ndcg {fmtMetric(m.ndcg)}
                    {" · "}grounded {fmtMetric(m.groundedness)} · complete {fmtMetric(m.completeness)} · p95 {String(m.p95_latency_ms)}ms
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {selectedRun && (
        <Modal title={`Run: ${selectedRun.name}`} onClose={() => setSelectedRun(null)}>
          {gate && (
            <div className={passed ? "success-box" : "error-box"} style={{ marginBottom: 12 }}>
              <strong>Gate: {passed ? "PASSED" : "FAILED"}</strong>
              <div className="mono" style={{ fontSize: 12 }}>
                {Object.entries((gate as { checks: Record<string, boolean> }).checks).map(([k, v]) => (
                  <div key={k}>
                    {v ? "✓" : "✗"} {k}
                  </div>
                ))}
              </div>
            </div>
          )}
          {itemsLoading && <div className="empty">Loading items…</div>}
          {items?.map((i) => (
            <div key={i.id} className="card" style={{ marginBottom: 10 }}>
              <div>
                <strong>{i.question}</strong>
              </div>
              {i.answer && <div className="muted mt" style={{ fontSize: 12, maxHeight: 80, overflow: "auto" }}>{i.answer}</div>}
              <div className="mono mt" style={{ fontSize: 11, color: "var(--text-dim)" }}>
                recall {fmtMetric(i.recall_at_k)} · precision {fmtMetric(i.precision_at_k)} · mrr {fmtMetric(i.mrr)} · ndcg {fmtMetric(i.ndcg)} · grounded {fmtMetric(i.groundedness)} · complete {fmtMetric(i.completeness)} · relevance {fmtMetric(i.relevance)} · {i.latency_ms}ms
              </div>
            </div>
          ))}
        </Modal>
      )}

      {goldenOpen && (
        <Modal title="Add golden question" onClose={() => setGoldenOpen(false)}>
          <form onSubmit={createGolden}>
            <div className="field">
              <label>Question *</label>
              <input value={question} onChange={(e) => setQuestion(e.target.value)} />
            </div>
            <div className="field">
              <label>Expected document ids (comma separated)</label>
              <input value={expectedDocs} onChange={(e) => setExpectedDocs(e.target.value)} placeholder="docid1, docid2" />
            </div>
            <div className="field">
              <label>Category</label>
              <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="optional" />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setGoldenOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || question.length < 5}>
                {busy ? "Saving…" : "Add"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {runOpen && (
        <Modal title="Start evaluation run" onClose={() => setRunOpen(false)}>
          <p className="muted">This runs the full offline pipeline: retrieve for each golden question, generate answers, score with the LLM judge. May take a few minutes.</p>
          <form onSubmit={startRun}>
            <div className="field">
              <label>Run name *</label>
              <input value={runName} onChange={(e) => setRunName(e.target.value)} placeholder="Release gate run" />
            </div>
            <div className="field">
              <label>RAG version</label>
              <input value={ragVersion} onChange={(e) => setRagVersion(e.target.value)} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setRunOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || runName.length < 2}>
                {busy ? "Starting…" : "Start run"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
