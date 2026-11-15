export type Product = {
  id: number; original_url: string; affiliate_url: string; marketplace: string; category: string; notes: string;
  title: string; description: string; image_url: string; price: number|null; original_price: number|null;
  price_note: string; data_source: string; captured_at: string|null; store: string; availability: string; tags: string[];
  status: string; created_at: string;
};
