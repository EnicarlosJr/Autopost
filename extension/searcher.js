// Buscas automáticas: pergunta ao Autopost qual busca está na hora, abre a página de
// resultados do Mercado Livre numa aba em segundo plano, lê os anúncios e devolve.
import {api} from './api.js';
import {log, sleep} from './config.js';

let running = false;
export function isSearching() { return running; }

async function waitTabReady(tabId, timeout = 25000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === 'complete') return;
    await sleep(500);
  }
}

async function readResults(url) {
  const tab = await chrome.tabs.create({url, active: false});
  try {
    await waitTabReady(tab.id);
    let last = null;
    for (let attempt = 0; attempt < 6; attempt++) {
      const [injection] = await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['search_reader.js']});
      last = injection?.result;
      if (last?.blocked || last?.items?.length) return last;
      await sleep(1500);
    }
    return last || {items: []};
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

// Categoria oficial de cada anúncio pelo preditor público do Mercado Livre (o card da busca não traz a categoria).
const PREDICTOR = 'https://api.mercadolibre.com/sites/MLB/domain_discovery/search?limit=1&q=';
const categoryCache = new Map();

async function predict(title) {
  const key = title.trim().toLowerCase().slice(0, 120);
  if (!key) return null;
  if (categoryCache.has(key)) return categoryCache.get(key);
  try {
    const response = await fetch(PREDICTOR + encodeURIComponent(title.slice(0, 120)), {credentials: 'omit'});
    if (!response.ok) return null;                        // limite ou bloqueio: o anúncio fica sem categoria
    const [best] = await response.json();
    const id = best?.category_id || null;
    categoryCache.set(key, id);
    if (categoryCache.size > 5000) categoryCache.delete(categoryCache.keys().next().value);
    return id;
  } catch { return null; }
}

/** Preenche ml_category_id nos itens, com no máximo 6 consultas ao mesmo tempo. */
export async function classify(items) {
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const item = items[next++];
      if (item.ml_category_id) continue;                  // já veio da página de resultados
      item.ml_category_id = await predict(item.title || '');
    }
  };
  await Promise.all(Array.from({length: Math.min(6, items.length)}, worker));
  return items;
}

async function readTerms(terms) {
  const items = [];
  let error = '';
  for (const [index, {term, url}] of terms.entries()) {
    if (index) await sleep(4000 + Math.random() * 5000);   // ritmo de pessoa, não de robô
    try {
      const result = await readResults(url);
      if (result.blocked) { error = 'O Mercado Livre pediu verificação. Abra o site neste Chrome e entre na sua conta.'; break; }
      items.push(...result.items.map(item => ({...item, term})));
    } catch (e) {
      error = `Falha ao ler "${term}": ${e.message || e}`;
    }
  }
  await classify(items);
  return {items: items.slice(0, 600), error};
}

/** Busca pedida dentro de uma campanha (tem prioridade: o usuário está esperando o resultado). */
export async function runDueCampaignSearch() {
  if (running) return {skipped: 'running'};
  const {apiToken} = await chrome.storage.local.get('apiToken');
  if (!apiToken) return {skipped: 'no-login'};
  running = true;
  try {
    const due = await api('/campaign-searches/due');
    if (!due) return {skipped: 'none'};
    log('busca da campanha', due.campaign_id, due.terms.map(t => t.term));
    const {items, error} = await readTerms(due.terms);
    const summary = await api(`/campaign-searches/${due.id}/results`, {method: 'POST', body: {items, error}});
    log('busca da campanha concluída', summary.status, summary.result_count, summary.matched_count);
    return summary;
  } catch (e) {
    log('erro na busca da campanha', e);
    return {error: e.message || String(e)};
  } finally {
    running = false;
  }
}

/** Roda no máximo uma busca por chamada. Termos da mesma busca são lidos com pausas entre eles. */
export async function runDueSearch() {
  if (running) return {skipped: 'running'};
  const {apiToken} = await chrome.storage.local.get('apiToken');
  if (!apiToken) return {skipped: 'no-login'};
  running = true;
  try {
    const due = await api('/searches/due');
    if (!due) return {skipped: 'none'};
    log('busca', due.name);
    const {items, error} = await readTerms(due.terms);
    const summary = await api(`/searches/${due.id}/results`, {method: 'POST', body: {items: items.slice(0, 500), error}});
    log('busca concluída', summary);
    return summary;
  } catch (e) {
    log('erro na busca', e);
    return {error: e.message || String(e)};
  } finally {
    running = false;
  }
}
