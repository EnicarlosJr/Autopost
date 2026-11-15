export type Search = {
  id: number; name: string; terms: string; exclude_terms: string;
  min_price: number | null; max_price: number | null; min_discount: number; min_rating: number | null;
  free_shipping_only: boolean; group_name: string; mode: 'approval' | 'auto';
  interval_minutes: number; max_per_run: number; active: boolean;
  last_run_at: string | null; next_run_at: string | null; last_result: string; pending: number;
};

export type Listing = {
  id: number; external_id: string; search_id: number | null; term: string; url: string; title: string;
  image_url: string; seller: string; price: number | null; original_price: number | null; price_note: string;
  discount_pct: number | null; rating: number | null; sold: number | null; free_shipping: boolean;
  min_price_30d: number | null; score: number; matches: boolean; reject_reason: string; status: string;
  publication_id: number | null; first_seen_at: string; last_seen_at: string;
};

export type GroupSchedule = {
  group_name: string; categories?: string[]; ml_categories?: import('./campaign').OfficialCategory[]; active?: boolean; start_hour: number; end_hour: number; max_per_day: number; gap_minutes: number; repost_days: number;
};
