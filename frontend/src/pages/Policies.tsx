import { useState } from "react";
import type { FormEvent } from "react";
import { errMsg, permissionsApi } from "../lib/api";
import type { Policy } from "../lib/types";
import { Badge, Empty, ErrorBox, Modal, PageHead, SuccessBox, TableSkeleton, useAsync } from "../components/ui";

const EFFECTS = ["allow", "deny"];
const ACTIONS = ["read", "write"];

const RULE_HELP = `Rules are JSON. Shortcut form ({"path": value}) checks equality. For richer logic use operators.
{"subject.role": "student"}
{"eq": ["subject.role", "student"]}
{"subject.role": ["student", "lecturer"]}   → membership
{"in": ["subject.role", ["student", "lecturer"]]}
{"and": [{"subject.role": "lecturer"}, {"resource.classification": "restricted"}]}
{"or": [{"subject.role": "owner"}, {"subject.department": "admin"}]}
{"not": {"eq": ["subject.department", "hr"]}}
Available operators: eq, neq, in, contains, gt, lt, and/or, not. Paths: subject.*, resource.*`;

export default function Policies() {
  const { data: policies, loading, error: loadError, reload } = useAsync<Policy[]>(() => permissionsApi.policies(), []);
  const [createOpen, setCreateOpen] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [action, setAction] = useState("read");
  const [rule, setRule] = useState("{\"subject.role\": \"student\"}");
  const [effect, setEffect] = useState("allow");
  const [priority, setPriority] = useState(100);

  const [testId, setTestId] = useState<string | null>(null);
  const [testSubject, setTestSubject] = useState("{\"role\": \"student\"}");
  const [testResource, setTestResource] = useState("{\"classification\": \"public\"}");
  const [testResult, setTestResult] = useState<string>("");

  const doCreate = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      JSON.parse(rule);
    } catch {
      setError("Rule must be valid JSON");
      setBusy(false);
      return;
    }
    try {
      const p = await permissionsApi.createPolicy({ name, description, action, rule, effect, priority, is_active: true });
      setSuccess(`Policy "${p.name}" created`);
      setCreateOpen(false);
      setName("");
      setDescription("");
      setRule("{\"subject.role\": \"student\"}");
      reload();
    } catch (err) {
      setError(errMsg(err));
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (id: string) => {
    if (!confirm("Delete this policy?")) return;
    try {
      await permissionsApi.deletePolicy(id);
      reload();
    } catch (err) {
      setError(errMsg(err));
    }
  };

  const doTest = async () => {
    if (!testId) return;
    setTestResult("");
    try {
      const r = await permissionsApi.testPolicy(testId, { subject: JSON.parse(testSubject), resource: JSON.parse(testResource) });
      setTestResult(
        `Rule matches: ${r.data.matches} — effect: ${r.data.effect} — allowed: ${r.data.decision ? "YES" : "NO"}`,
      );
    } catch (err) {
      setError(errMsg(err));
    }
  };

  return (
    <div>
      <PageHead title="Access Policies" sub="Attribute-based access rules evaluated on every retrieval.">
        <button className="btn primary" onClick={() => setCreateOpen(true)}>
          + New policy
        </button>
      </PageHead>
      <ErrorBox msg={error || loadError} onClose={() => setError("")} />
      <SuccessBox msg={success} />

      <div className="card">
        {loading && <TableSkeleton rows={4} cols={5} />}
        {!loading && (!policies || policies.length === 0) && <Empty>No policies yet.</Empty>}
        {policies && policies.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Priority</th>
                <th>Name</th>
                <th>Action</th>
                <th>Effect</th>
                <th>Rule</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {policies.map((p) => (
                <tr key={p.id}>
                  <td>{p.priority}</td>
                  <td>{p.name}</td>
                  <td>{p.action}</td>
                  <td>
                    <Badge tone={p.effect === "allow" ? "green" : "red"}>{p.effect}</Badge>
                  </td>
                  <td className="mono">{p.rule.slice(0, 60)}</td>
                  <td>
                    <Badge tone={p.is_active ? "green" : "amber"}>{p.is_active ? "active" : "inactive"}</Badge>
                  </td>
                  <td>
                    <div className="row" style={{ justifyContent: "flex-end" }}>
                      <button className="btn sm" onClick={() => setTestId(p.id)}>
                        Test
                      </button>
                      <button className="btn sm danger" onClick={() => doDelete(p.id)}>
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

      {createOpen && (
        <Modal title="Create access policy" onClose={() => setCreateOpen(false)}>
          <form onSubmit={doCreate}>
            <div className="field">
              <label>Name *</label>
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="field">
              <label>Description</label>
              <input value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="grid cols-3">
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
              <div className="field">
                <label>Effect</label>
                <select value={effect} onChange={(e) => setEffect(e.target.value)}>
                  {EFFECTS.map((x) => (
                    <option key={x} value={x}>
                      {x}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>Priority</label>
                <input type="number" value={priority} onChange={(e) => setPriority(Number(e.target.value))} />
              </div>
            </div>
            <div className="field">
              <label>Rule (JSON)</label>
              <textarea value={rule} onChange={(e) => setRule(e.target.value)} style={{ minHeight: 90 }} />
              <div className="muted" style={{ fontSize: 12, marginTop: 6, whiteSpace: "pre-wrap" }}>
                {RULE_HELP}
              </div>
            </div>
            <div className="modal-actions">
              <button type="button" className="btn" onClick={() => setCreateOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="btn primary" disabled={busy || name.length < 2}>
                {busy ? "Creating…" : "Create policy"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {testId && (
        <Modal title="Test policy" onClose={() => setTestId(null)}>
          <div className="field">
            <label>Subject (JSON)</label>
            <textarea value={testSubject} onChange={(e) => setTestSubject(e.target.value)} style={{ minHeight: 60 }} />
          </div>
          <div className="field">
            <label>Resource (JSON)</label>
            <textarea value={testResource} onChange={(e) => setTestResource(e.target.value)} style={{ minHeight: 60 }} />
          </div>
          {testResult && <div className="success-box">{testResult}</div>}
          <div className="modal-actions">
            <button className="btn" onClick={() => setTestId(null)}>
              Close
            </button>
            <button className="btn primary" onClick={doTest}>
              Evaluate
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
