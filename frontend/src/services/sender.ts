// Ponte com a extensão do Autopost (envio pelo WhatsApp Web e leitura de produtos pelo navegador).
import {API_BASE} from './api';

export type ExtensionStatus = {
  ready: boolean; version: string; logged_in: boolean; whatsapp_tab: boolean; sending: boolean; searching?: boolean;
  auto_send: boolean; send_interval_seconds: number; min_interval_seconds: number; next_send_in_seconds: number;
  queue_status: {text: string; at: number} | null;
};
export type SendResult = {sent: boolean; confirmed?: boolean; group: string; preview?: string};
export type BrowserCapture = {
  title: string; description: string; image_url: string; price: number|null; original_price: number|null;
  price_note: string; store: string; page_url: string; canonical_url?: string;
  regular_price?: number | null; price_conditions?: string; available?: boolean;
};

type Pending = {resolve: (value: any) => void; reject: (error: Error) => void; timer: number};
const pending = new Map<string, Pending>();
let extensionSeen = false;

window.addEventListener('message', event => {
  if (event.source !== window || event.origin !== location.origin) return;
  const data = event.data;
  if (!data || data.source !== 'autopost-extension') return;
  if (data.type === 'ready') { extensionSeen = true; return; }
  const item = pending.get(data.id);
  if (!item) return;
  pending.delete(data.id); clearTimeout(item.timer);
  if (data.ok) item.resolve(data.result); else item.reject(new Error(data.error || 'Falha na extensão.'));
});
window.postMessage({source: 'autopost-page', id: 'hello', type: 'hello'}, location.origin);

function callExtension<T>(type: string, payload?: unknown, timeout = 3000): Promise<T> {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      pending.delete(id);
      reject(new Error(extensionSeen
        ? 'A extensão não respondeu a tempo. Aperte F5 nesta página; se continuar, abra chrome://extensions e recarregue a extensão do Autopost.'
        : 'Extensão do Autopost não encontrada neste navegador.'));
    }, timeout);
    pending.set(id, {resolve, reject, timer});
    window.postMessage({source: 'autopost-page', id, type, payload}, location.origin);
  });
}

// Informa à extensão o endereço da API usado por este painel.
setTimeout(() => { callExtension('config', {api: API_BASE}).catch(() => {}); }, 500);

export async function extensionStatus(): Promise<ExtensionStatus | null> {
  try { return await callExtension<ExtensionStatus>('ping', undefined, 1500); } catch { return null; }
}

/** Reserva, confere o preço se preciso, envia pelo WhatsApp Web e registra o resultado (tudo na extensão). */
export function sendPublication(id: number, useOpenChat = false): Promise<SendResult> {
  return callExtension<SendResult>('sendPublication', {id, useOpenChat}, 180000);
}

/** Ensaio sem enviar: abre o grupo, cola o texto (ou a foto com legenda), confere e apaga. */
export function testSendInWhatsApp(id: number): Promise<{ok: boolean; preview?: string; composer?: string}> {
  return callExtension('testSend', {publication_id: id}, 180000);
}

/** Abre o produto numa aba em segundo plano e lê nome, imagem e preços. */
export function captureInBrowser(url: string, affiliateUrl?: string): Promise<BrowserCapture> {
  return callExtension<BrowserCapture>('capture', {url, affiliate_url: affiliateUrl}, 90000);
}

export function setAutoSend(enabled: boolean, intervalSeconds?: number): Promise<ExtensionStatus> {
  return callExtension<ExtensionStatus>('setAutoSend', {enabled, intervalSeconds}, 5000);
}

/** Pede para a extensão rodar agora a próxima busca automática que estiver na hora. */
export function runSearches(): Promise<{message?: string; skipped?: string; error?: string} | null> {
  return callExtension('runSearches', undefined, 240000);
}

/** Baixa a árvore oficial de categorias do Mercado Livre pelo navegador e envia ao Autopost. */
export function syncCategoriesInBrowser(): Promise<{total: number; roots: number; created: number; inactivated: number}> {
  return callExtension('syncCategories', undefined, 240000);
}

/** Lê o produto e gera o link de afiliado (meli.la) pela barra de afiliados. Só quando você clica. */
export function captureWithAffiliateLink(url: string): Promise<BrowserCapture & {affiliate_link?: string}> {
  return callExtension('capture', {url, affiliate: true}, 150000);
}

/** Roda agora a próxima busca de equivalentes das listas escolares (lê o Mercado Livre no seu Chrome). */
export function runSchoolSearch(): Promise<{status?: string; skipped?: string; error?: string} | null> {
  return callExtension('runSchoolSearch', undefined, 240000);
}
