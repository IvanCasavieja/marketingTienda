export type Platform = "meta" | "google_ads" | "tiktok" | "dv360" | "sfmc" | "google_analytics";

export interface CampaignMetric {
  platform: Platform;
  campaign_id: string;
  campaign_name: string;
  date: string;
  impressions: number;
  clicks: number;
  spend: number;
  conversions: number;
  revenue: number;
  reach: number;
  ctr: number;
  cpc: number;
  cpm: number;
  roas: number;
}

export interface PlatformSummary {
  platform: Platform;
  impressions: number;
  clicks: number;
  spend: number;
  conversions: number;
  revenue: number;
  avg_ctr: number;
  avg_roas: number;
}

export interface Ga4FunnelTotals {
  sessions: number;
  users: number;
  page_views: number;
  view_item: number;
  add_to_cart: number;
  begin_checkout: number;
  purchase: number;
  new_buyers: number;
  revenue: number;
  engagement_rate: number;
  avg_session_duration_sec: number;
  avg_order_value: number;
}

export interface Ga4ChannelRow extends Ga4FunnelTotals {
  channel: string;
}

export interface Ga4DailyRow {
  date: string;
  sessions: number;
  users: number;
  purchase: number;
  revenue: number;
  avg_order_value: number;
}

export interface Ga4FunnelResponse {
  totals: Ga4FunnelTotals;
  by_channel: Ga4ChannelRow[];
  daily: Ga4DailyRow[];
}

export interface Analysis {
  id: number;
  analysis_type: string;
  platforms: string[];
  date_from: string;
  date_to: string;
  result?: string;
  created_at: string;
}

export interface Connection {
  id: number;
  platform: Platform;
  account_id: string;
  account_name: string | null;
  is_active: boolean;
}

export interface CurrentUser {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  is_superuser: boolean;
  role_id: number | null;
  role_name: string | null;
  permissions: string[];
  assigned_locales: string[];
}

export const PLATFORM_LABELS: Record<Platform | string, string> = {
  meta:              "Meta Ads",
  google_ads:        "Google Ads",
  tiktok:            "TikTok Ads",
  dv360:             "DV360",
  sfmc:              "Salesforce MC",
  google_analytics:  "Google Analytics",
};

export const PLATFORM_COLORS: Record<Platform | string, string> = {
  meta:              "#1877F2",
  google_ads:        "#4285F4",
  tiktok:            "#010101",
  dv360:             "#34A853",
  sfmc:              "#00A1E0",
  google_analytics:  "#FF9900",
};
