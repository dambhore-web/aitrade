import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import AnnouncementsPage from "./modules/announcements/AnnouncementsPage";
import AutomatedTradingPage from "./modules/announcement_trading/AutomatedTradingPage";
import EquityTradingPage from "./modules/equity_trading/EquityTradingPage";
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
        <li>
          <Link to="/equity">Equity Trading</Link> -- indicator-based candles, diagnostics, and signals (read-only)
        </li>
        <li>
          <Link to="/auto-trading">Announcement Auto-Trading</Link> -- automatic scan-classify-trade loop
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
            <NavLink to="/equity">Equity Trading</NavLink>
            <NavLink to="/auto-trading">Auto-Trading</NavLink>
          </nav>
          <main>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/announcements" element={<AnnouncementsPage />} />
              <Route path="/historical" element={<HistoricalPage />} />
              <Route path="/equity" element={<EquityTradingPage />} />
              <Route path="/auto-trading" element={<AutomatedTradingPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
