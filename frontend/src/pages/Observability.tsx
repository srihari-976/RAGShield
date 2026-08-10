import { useState } from "react";
import { observabilityApi } from "../lib/api";
import { Badge, Empty, ErrorBox, PageHead, useAsync } from "../components/ui";

interface TraceRow {
  id: string;
  request_id: string;
  span_name: string;
  duration_ms: number;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface SecurityEvent {
  id: string;
  action: string;
  user_id: string | null;
  query_text: string | null;
  decision: string | null;
  reason: string | null;
  created_at: string;
}

interface SecurityView {
  actions: Record<string, string>;
  counts: Record<string, number>;
  events: SecurityEvent[];
}

const SPAN_ICONS: Record<string, string> = {
  retrieval: "🔍",
  llm_stream: "⚡",
  grounding: "🛡️",
  authorize: "🔑",
  embed: "🧠",
  default: "·",
};

export default function Observability() {
  const { data: latency, loading: lLoading, error: lError } = useAsync<Record<string, unknown>>(() => observabilityApi.latency(24), []);
  const { data: traces, loading: tLoading, error: tError } = useAsync<TraceRow[]>(() => observabilityApi.traces(50), []);
  const { data: security, loading: sLoading, error: sError } = useAsync<SecurityView>(() => observabilityApi.security(24), []);
  const [error, setError] = useState("");

  const chatTotal = (latency?.chat_total as Record<string, number>) ?? {};

  const statCards = [
    { label: "p50 latency (24h)", value: chatTotal.p50, icon: "◐" },
    { label: "p95 latency (24h)", value: chatTotal.p95, icon: "◑" },
    { label: "p99 latency (24h)", value: chatTotal.p99, icon: "◐" },
    { label: "Requests (24h)", value: chatTotal.count, icon: "⇅" },
  ];

  return (
    <div>
      <PageHead title="Observability" sub="Latency percentiles, per-stage request traces and security events." />
      <ErrorBox msg={error || lError || tError || sError} onClose={() => setError("")} />

      <div className="grid cols-4 mb">
        {statCards.map((s) => (
          <div key={s.label} className="stat-card">
            <div className="stat-icon">{s.icon}</div>
            <div>
              <div className="stat-num">{lLoading ? "…" : s.value !== undefined ? `${s.value}${s.label.startsWith("p") ? "ms" : ""}` : "n/a"}</div>
              <div className="stat-label">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h3>Traces</h3>
          {tLoading && <div className="empty">Loading…</div>}
          {!tLoading && (!traces || traces.length === 0) && <Empty>No traces yet.</Empty>}
          <div className="trace-list">
            {traces?.map((t) => (
              <div key={t.id} className="trace-row">
                <span className="trace-icon">{SPAN_ICONS[t.span_name] ?? SPAN_ICONS.default}</span>
                <div className="trace-main">
                  <span className="chip">{t.span_name}</span>
                  <span className="mono muted">{t.request_id.slice(0, 12)}</span>
                </div>
                <div className="row">
                  <span className="mono">{t.duration_ms}ms</span>
                  <Badge tone={t.status === "ok" ? "green" : "red"}>{t.status}</Badge>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <h3>Security events</h3>
          {sLoading && <div className="empty">Loading…</div>}
          {!sLoading && security && (
            <>
              <div className="row" style={{ flexWrap: "wrap", marginBottom: 12 }}>
                {Object.entries(security.counts ?? {}).map(([k, v]) => (
                  <span key={k} className="chip">
                    {k}: {v}
                  </span>
                ))}
              </div>
              {(!security.events || security.events.length === 0) && <Empty>No security events in the last 24h.</Empty>}
              <div className="trace-list">
                {security.events?.map((e) => (
                  <div key={e.id} className="trace-row">
                    <span className="trace-icon">⚠</span>
                    <div className="trace-main">
                      <span className="chip">{e.action}</span>
                      {e.reason && <span className="muted" style={{ fontSize: 12 }}>{e.reason}</span>}
                    </div>
                    <div className="muted" style={{ fontSize: 12, whiteSpace: "nowrap" }}>
                      {new Date(e.created_at).toLocaleTimeString()}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
