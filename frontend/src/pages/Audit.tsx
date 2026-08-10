import { useState } from "react";
import { auditApi } from "../lib/api";
import { Badge, Empty, ErrorBox, PageHead, TableSkeleton, useAsync } from "../components/ui";

interface LogRow {
  id: string;
  user_id: string | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  query_text: string | null;
  decision: string | null;
  reason: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export default function Audit() {
  const { data: logs, loading, error } = useAsync<LogRow[]>(() => auditApi.logs(200), []);
  const [filter, setFilter] = useState("");

  const filtered = filter ? (logs ?? []).filter((l) => l.action.includes(filter)) : logs;

  return (
    <div>
      <PageHead title="Audit Logs" sub="Immutable action trail across the tenant." />
      <ErrorBox msg={error} />

      <div className="card mb toolbar">
        <div className="search-input">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            placeholder="Filter by action…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {filter && (
            <button className="btn sm" onClick={() => setFilter("")} title="Clear filter">
              ×
            </button>
          )}
        </div>
        {filter && <span className="muted" style={{ fontSize: 12 }}>{filtered?.length ?? 0} results</span>}
      </div>

      <div className="card">
        {loading && <TableSkeleton rows={8} cols={5} />}
        {!loading && (!filtered || filtered.length === 0) && <Empty>No audit entries.</Empty>}
        {filtered && filtered.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Action</th>
                <th>User</th>
                <th>Resource</th>
                <th>Decision</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((l) => (
                <tr key={l.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(l.created_at).toLocaleString()}</td>
                  <td>
                    <Badge tone={l.action.includes("denial") || l.decision === "denied" ? "red" : l.action.startsWith("auth") ? "amber" : "blue"}>
                      {l.action}
                    </Badge>
                  </td>
                  <td className="mono muted">{l.user_id ? l.user_id.slice(0, 8) : "system"}</td>
                  <td>
                    {l.resource_type && (
                      <span className="mono muted">
                        {l.resource_type} {l.resource_id?.slice(0, 8)}
                      </span>
                    )}
                  </td>
                  <td>{l.decision ?? "—"}</td>
                  <td className="td-details">
                    {l.query_text && <div className="muted detail-line">{l.query_text}</div>}
                    {l.reason && <div className="muted detail-line">{l.reason}</div>}
                    {l.metadata && Object.keys(l.metadata).length > 0 && (
                      <div className="mono detail-json">{JSON.stringify(l.metadata)}</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
