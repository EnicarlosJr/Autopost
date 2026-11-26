// Listas escolares: reconfere, no seu Chrome, o preço dos produtos escolhidos para as listas.
// Só lê a página do produto (de preferência a página de catálogo /p/MLB…, onde o próprio
// Mercado Livre mostra a melhor oferta do mesmo produto). Não gera link de afiliado: só confere
// se o link que já existe abre o produto. Nada sai da lista: com erro, o último preço continua.
import {api} from './api.js';
import {captureProduct} from './capture.js';
import {log} from './config.js';

const GAP_MS = 2 * 60 * 1000;   // no máximo uma leitura a cada 2 minutos
let running = false, lastRun = 0;
export function isRefreshingLists() { return running; }

/** O link de afiliado (meli.la) ainda leva a uma página de produto do Mercado Livre? null = não deu para saber. */
export async function checkAffiliateLink(link) {
  if (!/^https:\/\/meli\.la\//i.test(link || '')) return null;
  try {
    const response = await fetch(link, {redirect: 'follow', credentials: 'include', cache: 'no-store'});
    const final = new URL(response.url);
    const isStore = /(^|\.)mercadoli(vre|bre)\.com(\.br)?$/i.test(final.hostname);
    const isLogin = /\/(gz|jms|login|registration)\b/i.test(final.pathname);
    if (response.status === 404 || response.status === 410) return false;
    if (!response.ok || isLogin) return null;       // limite, instabilidade ou verificação: confere na próxima
    return isStore && final.pathname.length > 1;
  } catch {
    return null;
  }
}

export async function refreshNextListProduct({force = false} = {}) {
  if (running) return {skipped: 'busy'};
  if (!force && Date.now() - lastRun < GAP_MS) return {skipped: 'wait'};
  running = true; lastRun = Date.now();
  try {
    const {product} = await api('/school-lists/refresh/next');
    if (!product) return {skipped: 'none'};
    log('lista escolar: conferindo preço', product.url);
    const done = body => api(`/school-lists/refresh/${product.id}/done`, {method: 'POST', body}).catch(() => {});
    const linkOk = await checkAffiliateLink(product.affiliate_url);
    try {
      const data = await captureProduct({url: product.url, affiliate_url: product.affiliate_url});
      await api(`/products/${product.id}/browser-data`, {method: 'POST', body: data});
      if (data.available === false) {
        await done({error: 'Indisponível no Mercado Livre agora (acabou ou o anúncio foi pausado).', unavailable: true, link_ok: linkOk});
        return {unavailable: product.id};
      }
      await done({link_ok: linkOk});
      return {refreshed: product.id, price: data.price};
    } catch (error) {
      await done({error: (error.message || String(error)).slice(0, 480), link_ok: linkOk});
      return {failed: product.id, error: error.message};
    }
  } catch (error) {
    return {skipped: 'error', error: error.message};
  } finally {
    running = false;
  }
}
