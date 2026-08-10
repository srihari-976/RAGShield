import { useState } from "react";
import type { FormEvent } from "react";
import { errMsg, tenantsApi } from "../lib/api";
import type { TenantSummary } from "../lib/types";
import { Badge, Empty, ErrorBox, Modal, PageHead, SuccessBox, TableSkeleton, useAsync } from "../components/ui";

export default function Tenants() {
  const { data: tenants, loading, error: loadError, reload } = useAsync<TenantSummary[]>(() => tenantsApi.list(), []);
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [adminUser, setAdminUser] = useState("");
  const [adminPass, setAdminPass] = useState("");

  const doCreate = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = { name, description };
      if (adminUser && adminPass) {
        body.admin_username = adminUser;
        body.admin_password = adminPass;
      }
      const t = await tenantsApi.create(body);
      setSuccess(`Tenant "${t.name}" created`);
      setCreateOpen(false);
      setName("");
      setDescription("");
      setAdminUser("");
      setAdminPass("");
      reload();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHead
        title="Tenants"
        sub="Isolated workspaces (e.g. separate lecturer / student tenants). Requires tenant.manage."
      >
        <button className="btn primary" onClick={() => setCreateOpen(true)}>
          + New tenant
        </button>
      </PageHead>
      <ErrorBox msg={error || loadError} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="card">
        {loading && <TableSkeleton rows={4} cols={5} />}
        {!loading && (!tenants || tenants.length === 0) && <Empty>No tenants yet.</Empty>}
        {tenants && tenants.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Users</th>
                <th>Documents</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {tenants.map((t) => (
                <tr key={t.id}>
                  <td>
                    <div>{t.name}</div>
                    <div className="mono muted">{t.id}</div>
                  </td>
                  <td className="muted">{t.description || "—"}</td>
                  <td>{t.user_count}</td>
                  <td>{t.document_count}</td>
                  <td>
                    <Badge tone={t.is_active ? "green" : "red"}>{t.is_active ? "active" : "disabled"}</Badge>
                  </td>
                  <td>{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {createOpen && (
        <Modal title="Create tenant workspace" onClose={() => setCreateOpen(false)}>
          <form onSubmit={doCreate}>
            <div className="field">
              <label>Name *</label>
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. ENGR-220 Students" />
            </div>
            <div className="field">
              <label>Description</label>
              <input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <hr className="hr" />
            <p className="muted" style={{ marginTop: 0 }}>
              Optional: bootstrap the tenant with its own admin account.
            </p>
            <div className="field">
              <label>Admin username</label>
              <input value={adminUser} onChange={(e) => setAdminUser(e.target.value)} />
            </div>
            <div className="field">
              <label>Admin password (min 8 chars)</label>
              <input type="password" value={adminPass} onChange={(e) => setAdminPass(e.target.value)} />
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setCreateOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || name.trim().length < 2}>
                {busy ? "Creating…" : "Create tenant"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
