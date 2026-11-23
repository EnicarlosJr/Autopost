export type {Product} from './product';

export type ProductBrief = {
  id: number; title: string; image_url: string; original_url: string; affiliate_url: string;
  price: number|null; original_price: number|null; price_note: string; status: string; captured_at: string|null;
};

export type Publication = {
  id: number; product_id: number; message: string; group_name: string; status: string;
  created_at: string; scheduled_at: string|null; sent_at: string|null; approved_at: string|null;
  send_attempts: number; last_error: string; product: ProductBrief|null; campaign_id?: number|null; send_mode?: 'preview' | 'image'; send_mode_choice?: 'preview' | 'image' | null;
  outgoing_message?: string;   // exatamente o que vai para o grupo (com o #publi no topo)
};

export type Settings = {
  id: number; name: string; enabled: boolean; process_on_create: boolean; generate_publication: boolean;
  require_approval: boolean; categories: string[]; marketplaces: string[]; whatsapp_group_name: string;
  message_template: string; default_template: string;
  send_mode: 'preview' | 'image'; watermark_text: string; watermark_handle: string;
  disclosure_text: string; show_discount: boolean;
};

export type Log = {id: number; task_id: string; task_type: string; product_id: number|null; status: string; attempt: number; detail: string; created_at: string};

export type Summary = Record<string, number>;
