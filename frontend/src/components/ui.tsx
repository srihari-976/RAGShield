import { useEffect, useId } from "react";
import type { DragEvent, ReactNode } from "react";
import { useState } from "react";

export function Spinner() {
  return <span className="spinner" />;
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function FilePicker({
  file,
  onChange,
  accept,
}: {
  file: File | null;
  onChange: (f: File | null) => void;
  accept?: string;
}) {
  const [dragging, setDragging] = useState(false);
  const id = useId();

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) onChange(f);
  };

  const ext = file ? (file.name.split(".").pop() || "file").slice(0, 5) : "";

  return (
    <div>
      <input
        id={id}
        type="file"
        accept={accept}
        style={{ display: "none" }}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      {file ? (
        <div className="file-card">
          <div className="file-type">{ext}</div>
          <div className="file-meta">
            <div className="file-name">{file.name}</div>
            <div className="muted" style={{ fontSize: 12 }}>
              {fmtBytes(file.size)}
            </div>
          </div>
          <button type="button" className="btn sm danger" onClick={() => onChange(null)} title="Remove file">
            ×
          </button>
        </div>
      ) : (
        <label
          htmlFor={id}
          className={`dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <svg
            width="26"
            height="26"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <path d="M17 8l-5-5-5 5M12 3v12" />
          </svg>
          <div>
            <strong>Click to choose a file</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              or drag &amp; drop · PDF, DOCX, XLSX, XLS, TXT, MD, HTML, JSON, CSV
            </div>
          </div>
        </label>
      )}
    </div>
  );
}

export function Skeleton({ width = "100%", height = 14 }: { width?: string | number; height?: number }) {
  return <div className="skeleton" style={{ width, height }} />;
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div style={{ padding: 6 }}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="row" style={{ padding: "12px 6px", borderBottom: "1px solid var(--border)", gap: 18 }}>
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} width={`${Math.floor(60 / cols) + ((r + c) % 3) * 6}%`} height={13} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}

export function ErrorBox({ msg, onClose }: { msg: string; onClose?: () => void }) {
  if (!msg) return null;
  return (
    <div className="error-box">
      <span>
        <strong>⚠ </strong>
        {msg}
      </span>
      {onClose && (
        <button className="btn sm" onClick={onClose}>
          ×
        </button>
      )}
    </div>
  );
}

export function SuccessBox({ msg }: { msg: string }) {
  if (!msg) return null;
  return (
    <div className="success-box">
      <span>
        <strong>✓ </strong>
        {msg}
      </span>
    </div>
  );
}

export function Badge({ tone, children }: { tone?: "green" | "amber" | "red" | "blue"; children: ReactNode }) {
  return <span className={`badge ${tone ?? ""}`}>{children}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function PageHead({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {children && <div>{children}</div>}
    </div>
  );
}

export function useAsync<T>(fn: () => Promise<unknown>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    fn()
      .then((res) => {
        const unwrapped =
          res && typeof res === "object" && "data" in (res as { data?: unknown }) ? (res as { data: T }).data : res;
        if (alive) setData(unwrapped as T);
      })
      .catch((e) => {
        if (alive) setError(String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, reload]);

  return { data, loading, error, setError, reload: () => setReload((n) => n + 1) };
}
