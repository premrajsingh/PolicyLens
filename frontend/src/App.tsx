import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import KnowledgeBase from "./pages/KnowledgeBase";
import Workspace from "./pages/Workspace";
import Evidence from "./pages/Evidence";
import Compare from "./pages/Compare";
import Settings from "./pages/Settings";

function GraphRedirect() {
  const location = useLocation();
  return <Navigate to={{ pathname: "/workspace", search: location.search }} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="knowledge-base" element={<KnowledgeBase />} />
          <Route path="workspace" element={<Workspace />} />
          <Route path="evidence" element={<Evidence />} />
          <Route path="graph" element={<GraphRedirect />} />
          <Route path="compare" element={<Compare />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
