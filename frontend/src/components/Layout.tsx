import { NavLink, Outlet } from "react-router-dom";
import type { ReactNode } from "react";
import { useAuth } from "../context/AuthContext";

interface NavItem {
  to: string;
  label: string;
  perm?: string;
  group: string;
  icon: ReactNode;
}

const I = ({ children }: { children: ReactNode }) => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {children}
  </svg>
);

const NAV: NavItem[] = [
  {
    to: "/chat",
    label: "Chat",
    group: "Workspace",
    icon: (
      <I>
        <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
      </I>
    ),
  },
  {
    to: "/documents",
    label: "Documents",
    perm: "document.read",
    group: "Workspace",
    icon: (
      <I>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
      </I>
    ),
  },
  {
    to: "/permissions",
    label: "Document Permissions",
    perm: "permission.manage",
    group: "Workspace",
    icon: (
      <I>
        <circle cx="7.5" cy="15.5" r="4.5" />
        <path d="M21 2l-9.6 9.6M15.5 7.5l3 3L22 7l-3-3" />
      </I>
    ),
  },
  {
    to: "/policies",
    label: "Access Policies",
    perm: "policy.manage",
    group: "Workspace",
    icon: (
      <I>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <path d="M9 12l2 2 4-4" />
      </I>
    ),
  },
  {
    to: "/users",
    label: "Users",
    perm: "user.create",
    group: "Administration",
    icon: (
      <I>
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </I>
    ),
  },
  {
    to: "/tenants",
    label: "Tenants",
    perm: "tenant.manage",
    group: "Administration",
    icon: (
      <I>
        <path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h1M9 13h1M9 17h1M14 9h1M14 13h1M14 17h1" />
      </I>
    ),
  },
  {
    to: "/models",
    label: "Models",
    perm: "model.manage",
    group: "Administration",
    icon: (
      <I>
        <rect x="6" y="6" width="12" height="12" rx="2" />
        <path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4" />
      </I>
    ),
  },
  {
    to: "/settings",
    label: "Prompts & Experiments",
    perm: "settings.manage",
    group: "Administration",
    icon: (
      <I>
        <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" />
      </I>
    ),
  },
  {
    to: "/evaluation",
    label: "Evaluation",
    perm: "evaluation.manage",
    group: "Administration",
    icon: (
      <I>
        <path d="M12 20a8 8 0 1 1 8-8" />
        <path d="M20 20l-8-8M12 8v4l3 3" />
      </I>
    ),
  },
  {
    to: "/observability",
    label: "Observability",
    perm: "observability.view",
    group: "Administration",
    icon: (
      <I>
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
      </I>
    ),
  },
  {
    to: "/audit",
    label: "Audit Logs",
    perm: "audit.view",
    group: "Administration",
    icon: (
      <I>
        <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
      </I>
    ),
  },
];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts.slice(0, 2).map((p) => p[0].toUpperCase()).join("");
}

export default function Layout() {
  const { identity, logout } = useAuth();

  const groups = [...new Set(NAV.map((n) => n.group))];
  const name = identity?.full_name || identity?.username || "user";

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2 3 7v10l9 5 9-5V7l-9-5Z" strokeLinejoin="round" />
              <path d="M8 12.5 11 15l5-6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          RAG<span>Shield</span>
        </div>
        <nav>
          {groups.map((g) => (
            <div key={g}>
              <div className="nav-label">{g}</div>
              {NAV.filter((n) => n.group === g)
                .filter((n) => !n.perm || identity?.is_admin || identity?.permissions.includes(n.perm))
                .map((n) => (
                  <NavLink key={n.to} to={n.to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
                    {n.icon}
                    <span>{n.label}</span>
                  </NavLink>
                ))}
            </div>
          ))}
        </nav>
        <div className="user-box">
          <div className="row-between">
            <div className="row">
              <div className="avatar">{initials(name)}</div>
              <div>
                <div className="name">{name}</div>
                <div className="role">{(identity?.roles || []).join(", ") || "user"}</div>
              </div>
            </div>
            <button className="btn sm" onClick={logout} title="Logout">
              Logout
            </button>
          </div>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
