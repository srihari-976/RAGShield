import { useState } from "react";
import { errMsg, modelsApi } from "../lib/api";
import { Badge, ErrorBox, PageHead, Skeleton, SuccessBox, useAsync } from "../components/ui";

interface ModelConfigRow {
  id: string;
  kind: string;
  model: string;
  is_default: boolean;
  enabled: boolean;
}

export default function Models() {
  const { data: overview, loading: ovLoading, error: ovError, reload } = useAsync<Record<string, unknown>>(() => modelsApi.list(), []);
  const { data: config, loading: cfgLoading, error: cfgError, reload: reloadCfg } = useAsync<ModelConfigRow[]>(() => modelsApi.config(), []);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [chatModel, setChatModel] = useState("");
  const [embedModel, setEmbedModel] = useState("");

  const installed = (overview?.installed as string[]) ?? [];
  const defaultChat = (overview?.default_chat as string) ?? "";
  const defaultEmbed = (overview?.default_embedding as string) ?? "";
  const reachable = Boolean(overview?.reachable);

  const selectedChat = chatModel || defaultChat;
  const selectedEmbed = embedModel || defaultEmbed;

  const save = async () => {
    if (!chatModel && !embedModel) return;
    setBusy(true);
    setError("");
    try {
      await modelsApi.update({ chat_model: chatModel || undefined, embedding_model: embedModel || undefined });
      setSuccess("Model configuration updated");
      setChatModel("");
      setEmbedModel("");
      reload();
      reloadCfg();
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHead title="Models" sub="Configure the LLM used for chat and the embedding model." />
      <ErrorBox msg={error || ovError || cfgError} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="grid cols-2">
        <div className="card">
          <h3>Ollama status</h3>
          <p>
            <Badge tone={reachable ? "green" : "red"}>{reachable ? "reachable" : "unreachable"}</Badge>
          </p>
          <div className="mono muted">Installed models:</div>
          <div className="mt">
            {(installed.length > 0 && installed.map((m) => <span key={m} className="chip">{m}</span>)) || (
              <span className="muted">none detected</span>
            )}
          </div>
        </div>

        <div className="card">
          <h3>Defaults</h3>
          {cfgLoading || ovLoading ? (
            <div>
              <Skeleton height={16} />
              <Skeleton height={16} width="75%" />
              <Skeleton height={34} width="40%" />
            </div>
          ) : (
            <>
              <div className="field">
                <label>Chat model</label>
                <select value={selectedChat} onChange={(e) => setChatModel(e.target.value)}>
                  <option value={defaultChat}>Default: {defaultChat}</option>
                  {installed.filter((m) => m !== defaultChat).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Embedding model</label>
                <select value={selectedEmbed} onChange={(e) => setEmbedModel(e.target.value)}>
                  <option value={defaultEmbed}>Default: {defaultEmbed}</option>
                  {installed.filter((m) => m !== defaultEmbed).map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <button className="btn primary" onClick={save} disabled={busy || (!chatModel && !embedModel)}>
                {busy ? "Saving…" : "Save defaults"}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="card mt">
        <h3>Registered configurations</h3>
        {config && config.length > 0 ? (
          <table className="table">
            <thead>
              <tr>
                <th>Kind</th>
                <th>Model</th>
                <th>Default</th>
                <th>Enabled</th>
              </tr>
            </thead>
            <tbody>
              {config.map((c) => (
                <tr key={c.id}>
                  <td>{c.kind}</td>
                  <td className="mono">{c.model}</td>
                  <td>{c.is_default ? <Badge tone="blue">default</Badge> : "—"}</td>
                  <td>
                    <Badge tone={c.enabled ? "green" : "red"}>{c.enabled ? "enabled" : "disabled"}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="empty">No configurations registered.</div>
        )}
      </div>
    </div>
  );
}
