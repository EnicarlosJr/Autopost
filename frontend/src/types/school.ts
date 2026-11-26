export type SchoolSection = 'coletivo' | 'individual';

export type SchoolOption = {
  slot: number; label: string; buy_qty: number; watch: boolean; last_error: string;
  product_id: number; title: string; status: string; price: number | null; original_price: number | null; price_note: string;
  store: string; image_url: string; image_source_url: string; original_url: string; affiliate_url: string;
  has_affiliate_link: boolean; catalog_id: string; captured_at: string | null;
  regular_price: number | null; price_conditions: string; unavailable: boolean; affiliate_ok: boolean | null;
};

export type SchoolSuggestion = {
  listing_id: number; external_id: string; url: string; link: string; title: string; price: number; original_price: number | null;
  price_note: string; image_url: string; seller: string; rating: number | null; sold: number | null; official_store: boolean;
  fulfillment: boolean; free_shipping: boolean; catalog_product_id: string | null; score: number; signals: string[];
};

export type SchoolSearch = {
  id: number; status: 'queued' | 'running' | 'done' | 'no_results' | 'failed'; reason: string; error: string;
  created_at: string | null; finished_at: string | null; result_count: number; accepted: number; rejected: number;
  reasons: Record<string, number>; slots: Record<string, SchoolSuggestion[]>; cheaper: SchoolSuggestion[];
};

export type SchoolItem = {id: number; section: SchoolSection; name: string; requested: string; color: string; position: number; options: SchoolOption[]; search: SchoolSearch | null};

export type SchoolTotals = Record<string, {min: number; max: number; items: number; priced: number}>;

export type SchoolListSummary = {
  id: number; school: string; grade: string; year: number; notes: string; refresh_hours: number;
  totals: SchoolTotals; oldest_capture: string | null; missing_links: number; empty_items: number; item_count?: number;
  broken_links: number; unavailable: number; suggestions: number;
  public: boolean; turmas: string[]; contact: string; public_url: string; page_url: string; visitors: number;
};

export type SchoolList = SchoolListSummary & {items: SchoolItem[]};

export type SchoolVisitor = {
  id: number; list_id: number | null; school: string; student_name: string; turma: string; visits: number;
  created_at: string | null; last_seen_at: string | null;
};
