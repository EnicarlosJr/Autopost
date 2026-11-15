export type GroupTarget = {group: string; limit: number; categories: string[]; ml_categories?: OfficialCategory[]};
export type GroupSet = {id: number; name: string; groups: string[]; created_at: string; updated_at: string};

export type CampaignConfig = {
  name: string; niche_ids: number[]; ml_categories: OfficialCategory[]; include_keywords: string[]; exclude_keywords: string[];
  product_ids: number[]; categories: string[]; exclude_categories: string[]; tags: string[];
  tag_mode: 'any' | 'all'; exclude_tags: string[]; include_uncategorized: boolean; min_discount: number;
  groups: GroupTarget[]; strategy: 'sequential' | 'balanced' | 'category' | 'custom'; total_limit: number;
  block_size: number; interval_minutes: number; interval_max_minutes: number; start_at: string | null;
  start_hour: number; end_hour: number; weekdays: number[]; daily_limit: number; pause_every: number; pause_minutes: number;
  end_at: string | null; message_gap_seconds: number; reuse_days: number | null; group_daily_limit: number;
};

export type Campaign = CampaignConfig & {
  id: number; status: string; display_status: string; created_at: string; confirmed_at: string | null;
  counts: Record<string, number>; total: number; sent: number; failed: number; pending: number; progress: number;
  next_send: string | null; products_count?: number; searches_count?: number; niche_names?: string[];
};

export type CampaignPlan = {
  errors: string[]; warnings: string[]; matching: number; selected: number; messages: number;
  per_group: {group: string; count: number}[]; start: string | null; end: string | null; duration_minutes: number;
  items: {product_id: number; title: string; category: string; group: string; at: string}[];
};

export type CampaignOptions = {
  categories: {name: string; count: number}[]; tags: {name: string; count: number}[]; uncategorized: number;
  groups: {name: string; active: boolean; categories: string[]; ml_categories?: OfficialCategory[]}[];
};

export type OfficialCategory = {id: string; include_children: boolean; name?: string; path?: string; is_leaf?: boolean; active?: boolean};
export type SearchFilters = {min_price: number | null; max_price: number | null; min_discount: number; min_rating: number | null; free_shipping: boolean; allow_uncategorized: boolean};
export type CampaignSearch = {
  id: number; campaign_id: number; niche_id: number | null; niche_name: string; categories: OfficialCategory[]; keywords: string[];
  exclude_keywords: string[]; filters: SearchFilters; terms: string[]; status: 'queued' | 'running' | 'done' | 'no_results' | 'failed';
  result_count: number; matched_count: number; added_count: number; error: string; created_at: string; started_at: string | null; finished_at: string | null;
};
export type SearchResult = {
  listing_id: number; external_id: string; title: string; url: string; image_url: string; price: number | null; original_price: number | null;
  price_note: string; discount_pct: number | null; rating: number | null; sold: number | null; free_shipping: boolean; score: number; term: string;
  ml_category_id: string | null; category_name: string; category_path: string; matched: boolean; reason: string; in_campaign: boolean;
};
export type CampaignProductRow = {
  product_id: number; title: string; image_url: string; price: number | null; original_price: number | null; price_note: string;
  ml_category_id: string | null; category_name: string; category_path: string; tags: string[]; search_id: number | null; added_at: string; ready: boolean;
};
