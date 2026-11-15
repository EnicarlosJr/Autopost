// Envio de uma publicação: reserva, confere o preço se preciso, envia e registra o resultado.
// Usado tanto pelo botão do painel quanto pela fila automática.
import {api, ApiError} from './api.js';
import {captureProduct} from './capture.js';
import {getConfig, log} from './config.js';
import {nextSendIn, sendToWhatsApp, whatsappTab, isSending} from './whatsapp.js';

async function claim(id) {
  try {
    return await api(`/publications/${id}/claim`, {method: 'POST'});
  } catch (error) {
    if (!(error instanceof ApiError) || error.detail?.code !== 'stale_price') throw error;
    // Preço lido há muito tempo: relê a loja no navegador e tenta reservar de novo.
    log('conferindo preço antes do envio', error.detail);
    let data;
    try {
      data = await captureProduct({url: error.detail.url, affiliate_url: error.detail.affiliate_url});
    } catch (captureError) {
      const message = `Não consegui conferir o preço antes do envio: ${captureError.message}`;
      await api(`/publications/${id}/failed`, {method: 'POST', body: {error: message}}).catch(() => {});
      throw new Error(message);
    }
    await api(`/products/${error.detail.product_id}/browser-data`, {method: 'POST', body: data});
    try {
      return await api(`/publications/${id}/claim`, {method: 'POST'});
    } catch (retryError) {
      // Ex.: o preço mudou e o texto foi editado à mão; o motivo fica gravado na publicação.
      const current = await api(`/publications/${id}`).catch(() => null);
      throw new Error(current?.last_error || retryError.message);
    }
  }
}

const ML_HOST = /(^|\.)mercadolivre\.com\.br$/i;

function needsAffiliateLink(product) {
  if (!product) return false;
  try {
    if (!ML_HOST.test(new URL(product.original_url).hostname)) return false;
  } catch { return false; }
  const link = (product.affiliate_url || '').trim();
  return !link || link === product.original_url;
}

// Produtos vindos das buscas automáticas chegam sem link de afiliado: a extensão abre o
// produto no seu Chrome, clica em "Compartilhar" e grava o meli.la (com o preço atualizado).
async function ensureAffiliateLink(id) {
  const current = await api(`/publications/${id}`);
  if (!needsAffiliateLink(current.product)) return;
  log('gerando link de afiliado', current.product.original_url);
  try {
    const data = await captureProduct({url: current.product.original_url, affiliate: true});
    await api(`/products/${current.product.id}/browser-data`, {method: 'POST', body: data});
  } catch (error) {
    const message = `Não consegui gerar o link de afiliado: ${error.message}`;
    await api(`/publications/${id}/failed`, {method: 'POST', body: {error: message}}).catch(() => {});
    throw new Error(message);
  }
}

export async function sendPublication({id, useOpenChat = false}) {
  await ensureAffiliateLink(id);
  const publication = await claim(id);
  try {
    // Só o texto, no formato definido nas Configurações (sem foto).
    const result = await sendToWhatsApp({group: publication.group_name, message: publication.message, useOpenChat});
    const detail = `Prévia do link: ${result.preview || 'sem link'}. Mensagem vista na conversa: ${result.confirmed ? 'sim' : 'não confirmada'}.`;
    log('enviada', id, detail);
    await api(`/publications/${id}/sent`, {method: 'POST', body: {detail}});
    return {...result, publication_id: id};
  } catch (error) {
    if (error.code === 'no_preview') {
      // Link recém-criado costuma demorar para o WhatsApp ler: adia alguns minutos em vez de enviar sem prévia.
      const back = await api(`/publications/${id}/postpone`, {method: 'POST', body: {minutes: 5, reason: error.message}}).catch(() => null);
      const later = back?.status === 'scheduled' ? ' Nova tentativa em 5 min.' : '';
      log('adiada', id, error.message);
      throw new Error(error.message + later);
    }
    await api(`/publications/${id}/failed`, {method: 'POST', body: {error: error.message || String(error)}}).catch(() => {});
    throw error;
  }
}

// Fila automática: envia no máximo uma publicação por chamada, respeitando o intervalo.
let running = false;
export async function processQueueOnce() {
  const config = await getConfig();
  if (!config.autoSend || running || isSending()) return {skipped: 'idle'};
  running = true;
  try {
    if (await nextSendIn(config.sendIntervalSeconds) > 0) return {skipped: 'interval'};
    const queue = await api('/publications/queue?limit=1');
    if (!queue.length) { await setQueueStatus('Fila vazia.'); return {skipped: 'empty'}; }
    if (!await whatsappTab()) { await setQueueStatus('Envio automático parado: abra o WhatsApp Web em uma aba.'); return {skipped: 'no-tab'}; }
    const next = queue[0];
    try {
      const result = await sendPublication({id: next.id});
      await setQueueStatus(`Enviada para "${next.group_name}"${result.preview ? ` (prévia ${result.preview})` : ''}.`);
      return result;
    } catch (error) {
      await setQueueStatus(`Falha ao enviar para "${next.group_name}": ${error.message}`);
      return {error: error.message};
    }
  } catch (error) {
    await setQueueStatus(error.message);
    return {error: error.message};
  } finally {
    running = false;
  }
}

async function setQueueStatus(text) {
  await chrome.storage.local.set({queueStatus: {text, at: Date.now()}});
}
