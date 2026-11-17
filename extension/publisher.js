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
  // Só conta como link de afiliado o encurtado oficial (meli.la ou mercadolivre.com/sec). Um link comum do
  // Mercado Livre no lugar dele faria a mensagem sair sem comissão.
  const link = (product.affiliate_url || '').trim();
  return !/^https:\/\/(meli\.la|(www\.)?mercadolivre\.com(\.br)?\/sec)\//i.test(link);
}

// Produtos vindos das buscas automáticas chegam sem link de afiliado: a extensão abre o
// produto no seu Chrome, clica em "Compartilhar" e grava o meli.la (com o preço atualizado).
// Problemas de conta (não está logado como afiliado, verificação do Mercado Livre) não são culpa da
// publicação: a fila pausa por 10 min em vez de queimar a campanha inteira como "falha".
const ACCOUNT_PROBLEM = /barra de afiliados|pediu login|verifica[çc][aã]o|permiss[aã]o/i;
let accountBlockedUntil = 0;
export function accountBlocked() { return Date.now() < accountBlockedUntil; }

async function ensureAffiliateLink(id) {
  const current = await api(`/publications/${id}`);
  if (!needsAffiliateLink(current.product)) return;
  log('gerando link de afiliado', current.product.original_url);
  try {
    const data = await captureProduct({url: current.product.original_url, affiliate: true});
    if (!data.affiliate_link) throw new Error('O Mercado Livre não devolveu o link meli.la.');
    await api(`/products/${current.product.id}/browser-data`, {method: 'POST', body: data});
  } catch (error) {
    const message = `Não consegui gerar o link de afiliado: ${error.message}`;
    if (ACCOUNT_PROBLEM.test(error.message || '')) {
      accountBlockedUntil = Date.now() + 10 * 60 * 1000;
      const blocked = new Error(`${message} A fila pausou por 10 min; a publicação continua na fila.`);
      blocked.code = 'account';
      throw blocked;
    }
    // Falha passageira (página lenta, link não apareceu): tenta de novo em 5 min, até 3 vezes.
    const back = await api(`/publications/${id}/postpone`, {method: 'POST', body: {minutes: 5, reason: message}}).catch(() => null);
    throw new Error(message + (back?.status === 'scheduled' ? ' Nova tentativa em 5 min.' : ''));
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
    if (error.code === 'no_preview' || error.code === 'bad_text') {
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

// Preparação antecipada: gera o link de afiliado das próximas publicações (até 30 min antes do horário),
// uma por vez e só quando nada mais está rodando. Assim, na hora do envio, o computador só cuida do
// WhatsApp e o link já existe há alguns minutos (o WhatsApp monta a prévia de links novos com mais dificuldade).
const PREPARE_AHEAD_MS = 30 * 60 * 1000;
let preparing = false;
const failedPrepare = new Map();   // id -> horário da falha (tenta de novo depois de 10 min)
export async function prepareUpcoming() {
  if (preparing || running || isSending() || accountBlocked()) return {skipped: 'busy'};
  preparing = true;
  try {
    // "scheduled" vem em ordem de horário; "approved" já está liberada (mais urgente).
    const [scheduled, approved] = await Promise.all([api('/publications?status=scheduled&limit=50'), api('/publications?status=approved&limit=20')]);
    const rows = [...approved, ...scheduled];
    const limit = Date.now() + PREPARE_AHEAD_MS;
    const next = rows
      .filter(p => needsAffiliateLink(p.product) && (!p.scheduled_at || new Date(p.scheduled_at).getTime() <= limit))
      .filter(p => Date.now() - (failedPrepare.get(p.id) || 0) > 10 * 60 * 1000)
      .sort((a, b) => new Date(a.scheduled_at || 0) - new Date(b.scheduled_at || 0))[0];
    if (!next) return {skipped: 'none'};
    log('preparando link de afiliado com antecedência', next.id);
    try {
      const data = await captureProduct({url: next.product.original_url, affiliate: true});
      if (!data.affiliate_link) throw new Error('O Mercado Livre não devolveu o link meli.la.');
      await api(`/products/${next.product.id}/browser-data`, {method: 'POST', body: data});
      return {prepared: next.id};
    } catch (error) {
      if (ACCOUNT_PROBLEM.test(error.message || '')) accountBlockedUntil = Date.now() + 10 * 60 * 1000;
      failedPrepare.set(next.id, Date.now());   // na hora do envio tenta de novo, como antes
      log('falha ao preparar', next.id, error.message);
      return {error: error.message};
    }
  } catch (error) {
    return {error: error.message || String(error)};
  } finally {
    preparing = false;
  }
}

// Fila automática: envia no máximo uma publicação por chamada, respeitando o intervalo.
let running = false;
export async function processQueueOnce() {
  const config = await getConfig();
  if (!config.autoSend || running || isSending() || preparing) return {skipped: 'idle'};
  running = true;
  try {
    if (await nextSendIn(config.sendIntervalSeconds) > 0) return {skipped: 'interval'};
    if (accountBlocked()) return {skipped: 'account'};
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
