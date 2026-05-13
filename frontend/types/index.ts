export type Platform = "meta" | "google_ads" | "tiktok" | "dv360" | "sfmc";

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
  team_group_id: number | null;
  team_name: string | null;
  group_name: string | null;
  join_code: string | null;
  is_active: boolean;
  is_superuser: boolean;
}

export const PLATFORM_LABELS: Record<Platform | string, string> = {
  meta: "Meta Ads",
  google_ads: "Google Ads",
  tiktok: "TikTok Ads",
  dv360: "DV360",
  sfmc: "Salesforce MC",
};

export const PLATFORM_COLORS: Record<Platform | string, string> = {
  meta: "#1877F2",
  google_ads: "#4285F4",
  tiktok: "#010101",
  dv360: "#34A853",
  sfmc: "#00A1E0",
};
