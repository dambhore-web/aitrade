import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import AnnouncementsPage from "./modules/announcements/AnnouncementsPage";
import HistoricalPage from "./modules/historical/HistoricalPage";
import "./App.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function Home() {
  return (
    <div className="page">
      <h1>aitrade</h1>
      <p>Pick a module from the nav above.</p>
      <ul className="home-links">
        <li>
          <Link to="/announcements">Corporate Announcements</Link> -- live feed of BSE/NSE filings
        </li>
        <li>
          <Link to="/historical">Historical Data Extractor</Link> -- download OHLC history via Kite Connect
        </li>
      </ul>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="app-shell">
          <nav className="topbar">
            <span className="brand">
              <span className="brand-badge">AI</span> aitrade
            </span>
            <NavLink to="/" end>
              Home
            </NavLink>
            <NavLink to="/announcements">Announcements</NavLink>
            <NavLink to="/historical">Historical Data</NavLink>
          </nav>
          <main>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/announcements" element={<AnnouncementsPage />} />
              <Route path="/historical" element={<HistoricalPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
