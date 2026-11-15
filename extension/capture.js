// Leitura de produto: abre a página no navegador do usuário (aba em segundo plano),
// executa reader.js e fecha a aba. É a única leitura usada para lojas que bloqueiam o servidor.
import {log, sleep} from './config.js';

const CAPTURE_HOSTS = /(^|\.)(mercadolivre\.com\.br|mercadolivre\.com|mercadolibre\.com|meli\.la|amazon\.com\.br|amzn\.to|magazineluiza\.com\.br|magalu\.com|shopee\.com\.br)$/i;

async function waitTabReady(tabId, timeout = 20000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === 'complete') return;
    await sleep(500);
  }
  log('página ainda carregando após', timeout, 'ms; tentando ler mesmo assim');
}

export function canCapture(url) {
  try { const parsed = new URL(url); return parsed.protocol === 'https:' && CAPTURE_HOSTS.test(parsed.hostname); } catch { return false; }
}

export async function readTab(tabId) {
  const [injection] = await chrome.scripting.executeScript({target: {tabId}, files: ['reader.js'], injectImmediately: true});
  return injection?.result;
}

// Executada DENTRO da página do produto: clica em "Compartilhar" (barra de afiliados do
// Mercado Livre, visível quando você está logado como afiliado) e lê o link meli.la gerado.
async function generateAffiliateLink() {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const findLink = () => {
    for (const field of document.querySelectorAll('textarea, input')) {
      const match = (field.value || '').match(/https:\/\/meli\.la\/[A-Za-z0-9]+/);
      if (match) return match[0];
    }
    return '';
  };
  let button = null;
  for (let i = 0; i < 20 && !button; i++) {
    button = document.querySelector('button.generate_link_button')
      || [...document.querySelectorAll('nav.stripe button, .stripe button')].find(b => /compartilhar/i.test(b.textContent || ''));
    if (!button) await sleep(500);
  }
  if (!button) return {error: 'no_affiliate_bar'};
  button.click();
  for (let i = 0; i < 40; i++) {
    const link = findLink();
    if (link) {
      document.querySelector('.andes-tooltip-button-close')?.click();
      return {link};
    }
    await sleep(250);
  }
  return {error: 'no_link'};
}

export async function capture({url, affiliate = false}) {
  if (!canCapture(url)) throw new Error('A leitura pelo navegador funciona para Mercado Livre, Amazon, Magalu e Shopee.');
  log('abrindo produto', url);
  const tab = await chrome.tabs.create({url, active: false});
  try {
    await waitTabReady(tab.id);
    let data = null, lastError = '';
    for (let attempt = 0; attempt < 10; attempt++) {
      try {
        data = await readTab(tab.id);
        log('leitura', attempt + 1, data);
        if (data?.blocked || (data && data.price != null)) break;
      } catch (error) {
        lastError = error.message || String(error);
        log('falha ao ler a página', lastError);
        if (/cannot access|permission/i.test(lastError)) {
          throw new Error('A extensão não tem permissão para ler esta loja. Em chrome://extensions, abra "Detalhes" do Autopost e permita o acesso aos sites.');
        }
      }
      await sleep(1500);
    }
    if (!data) throw new Error(`Não consegui ler a página do produto.${lastError ? ' ' + lastError : ''}`);
    if (data.blocked) throw new Error('A loja pediu login ou verificação também no seu navegador. Abra o link, entre na sua conta e tente de novo.');
    if (data.price == null && !data.title) throw new Error('A página aberta não mostrou nome nem preço do produto.');
    if (affiliate) {
      const [injection] = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: generateAffiliateLink});
      const result = injection?.result || {};
      log('link de afiliado', result);
      if (result.error === 'no_affiliate_bar') {
        throw new Error('A barra de afiliados do Mercado Livre não apareceu. Entre na sua conta de afiliado neste Chrome e tente de novo.');
      }
      if (!result.link) throw new Error('O Mercado Livre não gerou o link de afiliado (meli.la). Tente de novo em alguns minutos.');
      data.affiliate_link = result.link;
    }
    return data;
  } finally {
    chrome.tabs.remove(tab.id).catch(() => {});
  }
}

/** Lê o produto pelo link original e, se falhar, pelo link de afiliado. */
export async function captureProduct({url, affiliate_url, affiliate = false}) {
  try { return await capture({url, affiliate}); }
  catch (error) {
    if (affiliate) throw error;
    if (affiliate_url && affiliate_url !== url && canCapture(affiliate_url)) return capture({url: affiliate_url});
    throw error;
  }
}

// Exposta só para os testes de ponta a ponta (tests_e2e).
export const __test_generateAffiliateLink = generateAffiliateLink;
