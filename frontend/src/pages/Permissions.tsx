import { useEffect, useState } from "react";
import { documentsApi, errMsg, permissionsApi, usersApi } from "../lib/api";
import type { DocumentPermission, DocumentSummary, RoleInfo, UserSummary } from "../lib/types";
import { Badge, Empty, ErrorBox, Modal, PageHead, SuccessBox, useAsync } from "../components/ui";

const ACTIONS = ["read", "write"];

export default function Permissions() {
  const { data: docs, loading: docsLoading, error: docsError } = useAsync<DocumentSummary[]>(() => documentsApi.list(), []);
  const { data: users } = useAsync<UserSummary[]>(() => usersApi.list(), []);
  const { data: roles } = useAsync<RoleInfo[]>(() => usersApi.roles(), []);

  const [selDoc, setSelDoc] = useState<string | null>(null);
  const { data: perms, loading: permsLoading, reload } = useAsync<DocumentPermission[]>(
    () => (selDoc ? permissionsApi.document(selDoc) : Promise.resolve([])),
    [selDoc],
  );

  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [grantOpen, setGrantOpen] = useState(false);
  const [principalType, setPrincipalType] = useState("user");
  const [principalId, setPrincipalId] = useState("");
  const [action, setAction] = useState("read");

  useEffect(() => {
    setError("");
    setSuccess("");
  }, [selDoc]);

  const grant = async () => {
    if (!selDoc) return;
    try {
      await permissionsApi.grant(selDoc, {
        document_id: selDoc,
        action,
        principal_type: principalType,
        principal_id: principalType === "everyone" ? null : principalId,
      });
      setSuccess("Permission granted");
      setGrantOpen(false);
      setPrincipalId("");
      reload();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  const revoke = async (p: DocumentPermission) => {
    if (!selDoc) return;
    if (!confirm(`Revoke ${p.principal_type}:${p.principal_id ?? "everyone"} (${p.action})?`)) return;
    try {
      await permissionsApi.revoke(selDoc, p.id);
      reload();
    } catch (e) {
      setError(errMsg(e));
    }
  };

  const principalLabel = (p: DocumentPermission) => {
    if (p.principal_type === "everyone") return "Everyone";
    if (p.principal_type === "role") return `role:${p.principal_id}`;
    const u = users?.find((x) => x.id === p.principal_id);
    return u ? u.username : `user:${p.principal_id?.slice(0, 8)}`;
  };

  return (
    <div>
      <PageHead title="Document Permissions" sub="Grant or revoke read/write access per document, per user or role." />
      <ErrorBox msg={error || docsError} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="grid cols-2">
        <div className="card">
          <h3>1. Select document</h3>
          {docsLoading && <div className="empty">Loading…</div>}
          {!docsLoading && docs && docs.length > 0 && (
            <div>
              <select value={selDoc ?? ""} onChange={(e) => setSelDoc(e.target.value)}>
                <option value="">Choose a document…</option>
                {docs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </select>
              {selDoc &&
                (() => {
                  const d = docs.find((x) => x.id === selDoc);
                  return d ? (
                    <div className="select-hint">
                      <span className="chip">{d.document_type}</span>
                      <Badge tone={d.classification === "public" ? "green" : d.classification === "restricted" ? "red" : "blue"}>
                        {d.classification}
                      </Badge>
                      <span className="muted">
                        {d.chunk_count} chunk{d.chunk_count === 1 ? "" : "s"} · v{d.version}
                      </span>
                    </div>
                  ) : null;
                })()}
            </div>
          )}
          {!docsLoading && (!docs || docs.length === 0) && <Empty>No documents.</Empty>}
          {selDoc && (
            <div className="mt">
              <button className="btn primary" onClick={() => setGrantOpen(true)}>
                + Grant access
              </button>
            </div>
          )}
        </div>

        <div className="card">
          <h3>2. Current grants</h3>
          {permsLoading && <div className="empty">Loading…</div>}
          {!permsLoading && !selDoc && <Empty>Select a document.</Empty>}
          {!permsLoading && selDoc && (!perms || perms.length === 0) && <Empty>No grants yet.</Empty>}
          {perms && perms.length > 0 && (
            <table className="table">
              <thead>
                <tr>
                  <th>Principal</th>
                  <th>Action</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {perms.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Badge tone={p.principal_type === "everyone" ? "amber" : "blue"}>{principalLabel(p)}</Badge>
                    </td>
                    <td>{p.action}</td>
                    <td>
                      <button className="btn sm danger" onClick={() => revoke(p)}>
                        Revoke
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {grantOpen && (
        <Modal title="Grant access" onClose={() => setGrantOpen(false)}>
          <div className="field">
            <label>Principal type</label>
            <select value={principalType} onChange={(e) => setPrincipalType(e.target.value)}>
              <option value="user">User</option>
              <option value="role">Role</option>
              <option value="everyone">Everyone in tenant</option>
            </select>
          </div>
          {principalType !== "everyone" && (
            <div className="field">
              <label>{principalType === "user" ? "User" : "Role"}</label>
              {principalType === "user" ? (
                <select value={principalId} onChange={(e) => setPrincipalId(e.target.value)}>
                  <option value="">Choose…</option>
                  {(users ?? []).map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.username}
                    </option>
                  ))}
                </select>
              ) : (
                <select value={principalId} onChange={(e) => setPrincipalId(e.target.value)}>
                  <option value="">Choose…</option>
                  {(roles ?? []).map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}
          <div className="field">
            <label>Action</label>
            <select value={action} onChange={(e) => setAction(e.target.value)}>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
          </div>
          <div className="modal-actions">
            <button className="btn" onClick={() => setGrantOpen(false)}>
              Cancel
            </button>
            <button className="btn primary" onClick={grant} disabled={principalType !== "everyone" && !principalId}>
              Grant
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
