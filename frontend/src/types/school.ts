export type SchoolSection = 'coletivo' | 'individual';

export type SchoolOption = {
  slot: number; label: string; buy_qty: number; watch: boolean; last_error: string;
  product_id: number; title: string; status: string; price: number | null; original_price: number | null; price_note: string;
  store: string; image_url: string; image_source_url: string; original_url: string; affiliate_url: string;
  has_affiliate_link: boolean; catalog_id: string; captured_at: string | null;
};

export type SchoolItem = {id: number; section: SchoolSection; name: string; requested: string; color: string; position: number; options: SchoolOption[]};

export type SchoolTotals = Record<string, {min: number; max: number; items: number; priced: number}>;

export type SchoolListSummary = {
  id: number; school: string; grade: string; year: number; notes: string; refresh_hours: number;
  totals: SchoolTotals; oldest_capture: string | null; missing_links: number; empty_items: number; item_count?: number;
};

export type SchoolList = SchoolListSummary & {items: SchoolItem[]};
