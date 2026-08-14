import { useEffect, useState } from "react";
import { apiGet } from "./shared/api";
import "./App.css";

interface HealthResponse {
  status: string;
  app: string;
  env: string;
}

function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<HealthResponse>("/health")
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="app-shell">
      <h1>aitrade</h1>
      <p>Phase 0 scaffold -- backend connectivity check.</p>
      {health && (
        <p style={{ color: "seagreen" }}>
          Backend reachable: {health.app} ({health.env}) -- {health.status}
        </p>
      )}
      {error && (
        <p style={{ color: "crimson" }}>
          Backend unreachable: {error}. Is `uvicorn app.main:app --port 8000`
          running in backend/?
        </p>
      )}
      {!health && !error && <p>Checking backend...</p>}
    </div>
  );
}

export default App;
