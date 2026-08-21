import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import AnnouncementTradingPage from "./modules/announcement_trading/AnnouncementTradingPage";
import BonusBuybackPage from "./modules/bonus_buyback/BonusBuybackPage";
import DashboardPage from "./modules/dashboard/DashboardPage";
import EquityTradingPage from "./modules/equity_trading/EquityTradingPage";
import HistoricalPage from "./modules/historical/HistoricalPage";
import NewsExtractorPage from "./modules/news_extractor/NewsExtractorPage";
import ScreenerPage from "./modules/screener/ScreenerPage";
import BacktestPage from "./modules/backtest/BacktestPage";
import RiskStrip from "./shared/RiskStrip";
import Sidebar from "./shared/Sidebar";
import "./shared/theme.css";
import "./shared/components.css";
import "./App.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="app-shell">
          <Sidebar />
          <main>
            <RiskStrip />
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/announcements" element={<AnnouncementTradingPage />} />
              <Route path="/historical" element={<HistoricalPage />} />
              <Route path="/equity" element={<EquityTradingPage />} />
              <Route path="/news-extractor" element={<NewsExtractorPage />} />
              <Route path="/bonus-buyback" element={<BonusBuybackPage />} />
              <Route path="/screener" element={<ScreenerPage />} />
              <Route path="/backtest" element={<BacktestPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
