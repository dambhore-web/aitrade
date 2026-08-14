export interface AnnouncementOut {
  id: number;
  captured_utc: string | null;
  announcement_time_ist: string | null;
  stock_name: string | null;
  bse_code: string | null;
  nse_symbol: string | null;
  exchange: string | null;
  title: string | null;
  message: string | null;
  link: string | null;
  pdf_url: string | null;
  pdf_path: string | null;
  sentiment_label: string | null;
  sentiment_score: number | null;
  category: string | null;
  is_bonus_buyback: number | null;
  financial_result_flag: number | null;
}

export interface AnnouncementsPageResponse {
  items: AnnouncementOut[];
  total: number;
  limit: number;
  offset: number;
}

export interface ListenerStatus {
  running: boolean;
  last_poll_utc: string | null;
  last_error: string | null;
  auth_expired: boolean;
}
