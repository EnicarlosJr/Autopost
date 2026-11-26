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
  send_mode: 'preview' | 'image'; watermark_text: string; watermark_handle: string;
  custom_style: boolean; message_template: string;   // falso = modelo e marca d'água do perfil
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
  /** Grupos em que a campanha passa do limite diário do cadastro do grupo (só aviso). */
  group_limits?: {group: string; limit: number; max_day: number}[];
};

export type CampaignOptions = {
  categories: {name: string; count: number}[]; tags: {name: string; count: number}[]; uncategorized: number;
  groups: {name: string; active: boolean; categories: string[]; ml_categories?: OfficialCategory[]}[];
};

export type OfficialCategory = {id: string; include_children: boolean; name?: string; path?: string; is_leaf?: boolean; active?: boolean};
export type Gender = 'any' | 'male' | 'female';
export const GENDER_LABEL: Record<Gender, string> = {any: 'Todos', male: 'Masculino', female: 'Feminino'};
export type SearchFilters = {min_price: number | null; max_price: number | null; min_discount: number; min_rating: number | null; free_shipping: boolean;
  allow_uncategorized: boolean; gender: Gender; gender_strict: boolean;
  trust: 'off' | 'basic' | 'high' | 'custom'; min_sold: number; official_or_full: boolean; exclude_suspicious: boolean;
  source?: 'search' | 'offers'; offers_pages?: number;
  /** Seções da área de ofertas do ML; vazio = Oferta do dia. */
  offer_kinds?: OfferKind[]; offers_rotate?: boolean; offers_start?: number; offers_by_category?: boolean; offers_match_keywords?: boolean;
  /** Pula produtos já anunciados (na fila ou enviados) nos últimos N dias; 0 = não pula. */
  skip_used_days?: number};
export type OfferKind = 'all' | 'lightning' | 'deal_of_the_day' | 'unbeatable' | 'outlet';
export const OFFER_KINDS: [OfferKind, string, string][] = [
  ['lightning', 'Ofertas relâmpago', 'Duram poucas horas; mudam ao longo do dia'],
  ['deal_of_the_day', 'Oferta do dia', 'Valem até a meia-noite'],
  ['unbeatable', 'Preços imbatíveis', 'Seleção do Mercado Livre com preço baixo'],
  ['outlet', 'Outlet', 'Produtos com desconto de saldo ou coleção passada'],
  ['all', 'Todas as ofertas', 'Tudo da área de ofertas (inclui as outras seções)'],
];
export type CampaignSearch = {
  id: number; campaign_id: number; niche_id: number | null; niche_name: string; categories: OfficialCategory[]; keywords: string[];
  exclude_keywords: string[]; filters: SearchFilters; terms: string[]; status: 'queued' | 'running' | 'done' | 'no_results' | 'failed';
  result_count: number; matched_count: number; added_count: number; error: string; created_at: string; started_at: string | null; finished_at: string | null;
};
export type SearchResult = {
  listing_id: number; external_id: string; title: string; url: string; image_url: string; price: number | null; original_price: number | null;
  price_note: string; discount_pct: number | null; rating: number | null; sold: number | null; free_shipping: boolean; score: number; term: string;
  ml_category_id: string | null; category_name: string; category_path: string; matched: boolean; reason: string; in_campaign: boolean;
  official_store?: boolean; fulfillment?: boolean; seller?: string;
  // Parecidos agrupados: o melhor de cada grupo (group_best) representa os outros.
  group_key?: number; group_size?: number; group_best?: boolean; cheapest?: boolean; similar_in_campaign?: boolean;
};
export type BestPick = {listing_ids: number[]; available: number; groups: number};
export type CampaignProductRow = {
  product_id: number; title: string; image_url: string; price: number | null; original_price: number | null; price_note: string;
  ml_category_id: string | null; category_name: string; category_path: string; tags: string[]; search_id: number | null; added_at: string; ready: boolean;
};
