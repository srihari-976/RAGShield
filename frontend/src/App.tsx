import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Chat from "./pages/Chat";
import Documents from "./pages/Documents";
import Permissions from "./pages/Permissions";
import Policies from "./pages/Policies";
import Users from "./pages/Users";
import Tenants from "./pages/Tenants";
import Models from "./pages/Models";
import Settings from "./pages/Settings";
import Evaluation from "./pages/Evaluation";
import Observability from "./pages/Observability";
import Audit from "./pages/Audit";

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { identity, loading } = useAuth();
  if (loading) {
    return (
      <div style={{ height: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <span className="spinner" />
      </div>
    );
  }
  if (!identity) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function AlreadyAuthed({ children }: { children: React.ReactNode }) {
  const { identity, loading } = useAuth();
  if (loading) return null;
  if (identity) return <Navigate to="/chat" replace />;
  return <>{children}</>;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route
            path="/login"
            element={
              <AlreadyAuthed>
                <Login />
              </AlreadyAuthed>
            }
          />
          <Route
            element={
              <RequireAuth>
                <Layout />
              </RequireAuth>
            }
          >
            <Route path="/chat" element={<Chat />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/permissions" element={<Permissions />} />
            <Route path="/policies" element={<Policies />} />
            <Route path="/users" element={<Users />} />
            <Route path="/tenants" element={<Tenants />} />
            <Route path="/models" element={<Models />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/evaluation" element={<Evaluation />} />
            <Route path="/observability" element={<Observability />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="/" element={<Navigate to="/chat" replace />} />
          </Route>
          <Route path="*" element={<Navigate to="/chat" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
