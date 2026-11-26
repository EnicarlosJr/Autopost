// Listas escolares: reconfere, no seu Chrome, o preço dos produtos escolhidos para as listas.
// Só lê a página do produto (de preferência a página de catálogo /p/MLB…, onde o próprio
// Mercado Livre mostra a melhor oferta do mesmo produto). Não gera link de afiliado.
import {api} from './api.js';
import {captureProduct} from './capture.js';
import {log} from './config.js';

const GAP_MS = 2 * 60 * 1000;   // no máximo uma leitura a cada 2 minutos
let running = false, lastRun = 0;
export function isRefreshingLists() { return running; }

export async function refreshNextListProduct({force = false} = {}) {
  if (running) return {skipped: 'busy'};
  if (!force && Date.now() - lastRun < GAP_MS) return {skipped: 'wait'};
  running = true; lastRun = Date.now();
  try {
    const {product} = await api('/school-lists/refresh/next');
    if (!product) return {skipped: 'none'};
    log('lista escolar: conferindo preço', product.url);
    try {
      const data = await captureProduct({url: product.url, affiliate_url: product.affiliate_url});
      await api(`/products/${product.id}/browser-data`, {method: 'POST', body: data});
      await api(`/school-lists/refresh/${product.id}/done`, {method: 'POST', body: {}});
      return {refreshed: product.id, price: data.price};
    } catch (error) {
      await api(`/school-lists/refresh/${product.id}/done`, {method: 'POST', body: {error: (error.message || String(error)).slice(0, 480)}}).catch(() => {});
      return {failed: product.id, error: error.message};
    }
  } catch (error) {
    return {skipped: 'error', error: error.message};
  } finally {
    running = false;
  }
}
