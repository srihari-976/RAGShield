import { useState } from "react";
import type { FormEvent } from "react";
import { errMsg, tenantsApi, usersApi } from "../lib/api";
import type { RoleInfo, TenantSummary, UserSummary } from "../lib/types";
import { Badge, Empty, ErrorBox, Modal, PageHead, SuccessBox, TableSkeleton, useAsync } from "../components/ui";

export default function Users() {
  const { data: users, loading, error: loadError, reload } = useAsync<UserSummary[]>(() => usersApi.list(), []);
  const { data: roles } = useAsync<RoleInfo[]>(() => usersApi.roles(), []);
  const { data: tenants } = useAsync<TenantSummary[]>(() => tenantsApi.list(), []);
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [department, setDepartment] = useState("");
  const [roleNames, setRoleNames] = useState<string[]>([]);
  const [tenantId, setTenantId] = useState("");

  const toggleRole = (r: string) =>
    setRoleNames((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));

  const doCreate = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = { username, email, password, full_name: fullName || undefined, department: department || undefined, roles: roleNames };
      if (tenantId) body.tenant_id = tenantId;
      await usersApi.create(body);
      setSuccess(`User "${username}" created`);
      setCreateOpen(false);
      setUsername("");
      setEmail("");
      setPassword("");
      setFullName("");
      setDepartment("");
      setRoleNames([]);
      setTenantId("");
      reload();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const doToggleActive = async (u: UserSummary) => {
    try {
      await usersApi.update(u.id, { is_active: !u.is_active });
      reload();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  return (
    <div>
      <PageHead title="Users" sub="Create and manage tenant users and their roles.">
        <button className="btn primary" onClick={() => setCreateOpen(true)}>
          + New user
        </button>
      </PageHead>
      <ErrorBox msg={error || loadError} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="card">
        {loading && <TableSkeleton rows={6} cols={5} />}
        {!loading && (!users || users.length === 0) && <Empty>No users yet.</Empty>}
        {users && users.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Name</th>
                <th>Email</th>
                <th>Department</th>
                <th>Roles</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id}>
                  <td>{u.username}</td>
                  <td>{u.full_name || "—"}</td>
                  <td>{u.email}</td>
                  <td>{u.department || "—"}</td>
                  <td>
                    {u.roles.map((r) => (
                      <span key={r} className="chip">
                        {r}
                      </span>
                    ))}
                  </td>
                  <td>
                    <Badge tone={u.is_active ? "green" : "red"}>{u.is_active ? "active" : "disabled"}</Badge>
                  </td>
                  <td>
                    <button className="btn sm" onClick={() => doToggleActive(u)}>
                      {u.is_active ? "Disable" : "Enable"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {createOpen && (
        <Modal title="Create user" onClose={() => setCreateOpen(false)}>
          <form onSubmit={doCreate}>
            <div className="grid cols-2">
              <div className="field">
                <label>Username *</label>
                <input value={username} onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="field">
                <label>Email *</label>
                <input value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
            </div>
            <div className="field">
              <label>Password * (min 8)</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            <div className="grid cols-2">
              <div className="field">
                <label>Full name</label>
                <input value={fullName} onChange={(e) => setFullName(e.target.value)} />
              </div>
              <div className="field">
                <label>Department</label>
                <input value={department} onChange={(e) => setDepartment(e.target.value)} />
              </div>
            </div>
            {tenants && tenants.length > 1 && (
              <div className="field">
                <label>Tenant (cross-tenant creation)</label>
                <select value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
                  <option value="">Current tenant</option>
                  {tenants.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div className="field">
              <label>Roles</label>
              <div>
                {(roles ?? []).map((r) => (
                  <label key={r.id} className="chip" style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
                    <input
                      type="checkbox"
                      checked={roleNames.includes(r.name)}
                      onChange={() => toggleRole(r.name)}
                      style={{ accentColor: "var(--accent)" }}
                    />
                    {r.name}
                  </label>
                ))}
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setCreateOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || username.length < 3 || !email || password.length < 8}>
                {busy ? "Creating…" : "Create user"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
