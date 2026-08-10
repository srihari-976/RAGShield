import { useState } from "react";
import type { FormEvent } from "react";
import { errMsg, settingsApi } from "../lib/api";
import { Badge, Empty, ErrorBox, Modal, PageHead, SuccessBox, useAsync } from "../components/ui";

interface PromptRow {
  id: string;
  version: string;
  system_prompt: string;
  is_active: boolean;
  created_at: string;
}

interface ExperimentRow {
  id: string;
  name: string;
  rag_version_a: string;
  rag_version_b: string;
  traffic_percent_b: number;
  is_active: boolean;
}

export default function Settings() {
  const { data: prompts, loading: pLoading, reload: reloadPrompts } = useAsync<PromptRow[]>(() => settingsApi.prompts(), []);
  const { data: experiments, loading: eLoading, reload: reloadExps } = useAsync<ExperimentRow[]>(() => settingsApi.experiments(), []);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  const [promptOpen, setPromptOpen] = useState(false);
  const [version, setVersion] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");

  const [expOpen, setExpOpen] = useState(false);
  const [expName, setExpName] = useState("");
  const [verA, setVerA] = useState("v1");
  const [verB, setVerB] = useState("v1");
  const [trafficB, setTrafficB] = useState(5);

  const createPrompt = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await settingsApi.createPrompt({ version, system_prompt: systemPrompt });
      setSuccess(`Prompt v${version} created and activated`);
      setPromptOpen(false);
      setVersion("");
      setSystemPrompt("");
      reloadPrompts();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const activate = async (v: string) => {
    try {
      await settingsApi.activatePrompt(v);
      setSuccess(`Prompt v${v} activated`);
      reloadPrompts();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const createExperiment = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await settingsApi.createExperiment({ name: expName, rag_version_a: verA, rag_version_b: verB, traffic_percent_b: trafficB });
      setSuccess(`Experiment "${expName}" created`);
      setExpOpen(false);
      setExpName("");
      reloadExps();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const toggleExp = async (id: string, active: boolean) => {
    try {
      await settingsApi.toggleExperiment(id, !active);
      reloadExps();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  return (
    <div>
      <PageHead
        title="Prompts & Experiments"
        sub="Version prompt templates and run canary A/B experiments between RAG versions."
      />
      <ErrorBox msg={error} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="grid cols-2">
        <div className="card">
          <div className="row-between mb">
            <h3>Prompt versions</h3>
            <button className="btn sm primary" onClick={() => setPromptOpen(true)}>
              + New version
            </button>
          </div>
          {pLoading && <div className="empty">Loading…</div>}
          {!pLoading && (!prompts || prompts.length === 0) && <Empty>No prompt versions.</Empty>}
          {prompts?.map((p) => (
            <div key={p.id} className="card" style={{ marginBottom: 10 }}>
              <div className="row-between">
                <strong>
                  v{p.version} {p.is_active && <Badge tone="green">active</Badge>}
                </strong>
                {!p.is_active && (
                  <button className="btn sm" onClick={() => activate(p.version)}>
                    Activate
                  </button>
                )}
              </div>
              <div className="mono muted mt" style={{ maxHeight: 120, overflow: "auto", whiteSpace: "pre-wrap" }}>
                {p.system_prompt}
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="row-between mb">
            <h3>Canary experiments</h3>
            <button className="btn sm primary" onClick={() => setExpOpen(true)}>
              + New experiment
            </button>
          </div>
          {eLoading && <div className="empty">Loading…</div>}
          {!eLoading && (!experiments || experiments.length === 0) && <Empty>No experiments.</Empty>}
          {experiments?.map((x) => (
            <div key={x.id} className="card" style={{ marginBottom: 10 }}>
              <div className="row-between">
                <strong>{x.name}</strong>
                <Badge tone={x.is_active ? "green" : "amber"}>{x.is_active ? "live" : "off"}</Badge>
              </div>
              <div className="muted mt">
                A: v{x.rag_version_a} · B: v{x.rag_version_b} · {x.traffic_percent_b}% traffic to B
              </div>
              <button className="btn sm mt" onClick={() => toggleExp(x.id, x.is_active)}>
                {x.is_active ? "Stop" : "Start"}
              </button>
            </div>
          ))}
        </div>
      </div>

      {promptOpen && (
        <Modal title="Create prompt version" onClose={() => setPromptOpen(false)}>
          <form onSubmit={createPrompt}>
            <div className="field">
              <label>Version label *</label>
              <input value={version} onChange={(e) => setVersion(e.target.value)} placeholder="v2" />
            </div>
            <div className="field">
              <label>System prompt *</label>
              <textarea value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)} style={{ minHeight: 140 }} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setPromptOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || version.length < 1 || systemPrompt.length < 10}>
                {busy ? "Creating…" : "Create & activate"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {expOpen && (
        <Modal title="Create canary experiment" onClose={() => setExpOpen(false)}>
          <form onSubmit={createExperiment}>
            <div className="field">
              <label>Name *</label>
              <input value={expName} onChange={(e) => setExpName(e.target.value)} />
            </div>
            <div className="grid cols-2">
              <div className="field">
                <label>Version A</label>
                <input value={verA} onChange={(e) => setVerA(e.target.value)} />
              </div>
              <div className="field">
                <label>Version B</label>
                <input value={verB} onChange={(e) => setVerB(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label>Traffic % to B</label>
              <input type="number" value={trafficB} onChange={(e) => setTrafficB(Number(e.target.value))} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setExpOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || expName.length < 2}>
                {busy ? "Creating…" : "Create"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
