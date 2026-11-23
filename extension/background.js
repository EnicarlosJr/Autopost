// Service worker da extensão: recebe pedidos do painel e do botão, e roda a fila automática.
import {captureProduct, capture, __test_generateAffiliateLink} from './capture.js';
import {getConfig, setConfig, MIN_INTERVAL_SECONDS} from './config.js';
import {prepareUpcoming, processQueueOnce, sendPublication} from './publisher.js';
import {isSearching, runDueCampaignSearch, runDueSearch} from './searcher.js';
import {syncCategories} from './catalog.js';
import {isSending, nextSendIn, sendToWhatsApp, whatsappTab, __test_sendInWhatsApp} from './whatsapp.js';
import {api, apiBase64} from './api.js';

// Usado pelos testes de ponta a ponta (tests_e2e) para exercitar o envio numa página simulada.
globalThis.__autopostTest = {sendInWhatsApp: __test_sendInWhatsApp, generateAffiliateLink: __test_generateAffiliateLink};

const ALARM = 'autopost-queue';

async function ensureAlarm() {
  if (!await chrome.alarms.get(ALARM)) chrome.alarms.create(ALARM, {periodInMinutes: 0.5});
}
chrome.runtime.onInstalled.addListener(ensureAlarm);
chrome.runtime.onStartup.addListener(ensureAlarm);
chrome.alarms.onAlarm.addListener(async alarm => {
  if (alarm.name !== ALARM) return;
  const sent = await processQueueOnce();
  if (isSending() || sent?.sent) return;
  // Sem envio agora: prepara o link de afiliado da próxima publicação e, se não havia nada, roda as buscas.
  const prepared = await prepareUpcoming();
  if (prepared?.prepared || prepared?.skipped === 'busy') return;
  // Buscas só rodam quando não há envio em andamento. As da campanha têm prioridade.
  if (!isSending() && !isSearching()) {
    const campaign = await runDueCampaignSearch();
    if (campaign?.skipped === 'none') runDueSearch();
  }
});
ensureAlarm();

async function status() {
  const config = await getConfig();
  const {apiToken, queueStatus} = await chrome.storage.local.get(['apiToken', 'queueStatus']);
  return {
    ready: true,
    version: chrome.runtime.getManifest().version,
    logged_in: Boolean(apiToken),
    whatsapp_tab: Boolean(await whatsappTab()),
    sending: isSending(),
    searching: isSearching(),
    auto_send: config.autoSend,
    send_interval_seconds: config.sendIntervalSeconds,
    min_interval_seconds: MIN_INTERVAL_SECONDS,
    next_send_in_seconds: await nextSendIn(),
    queue_status: queueStatus || null,
  };
}

async function handle(message, sender) {
  switch (message.type) {
    case 'ping': return status();
    case 'sendPublication': return sendPublication(message.payload || {});
    case 'capture': return captureProduct(message.payload || {});
    case 'captureUrl': return capture(message.payload || {});
    case 'runSearches': {
      const campaign = await runDueCampaignSearch();
      return campaign?.skipped === 'none' ? runDueSearch() : campaign;
    }
    case 'syncCategories': return syncCategories();
    case 'testSend': {
      // Ensaio sem enviar: abre o grupo, cola o texto (ou a foto com legenda), confere e apaga.
      const {publication_id: id, group} = message.payload || {};
      const publication = await api(`/publications/${id}`);
      const imageBase64 = publication.send_mode === 'image' ? await apiBase64(`/publications/${id}/image`) : '';
      return sendToWhatsApp({group: group || publication.group_name, message: publication.outgoing_message || publication.message, imageBase64, dryRun: true});
    }
    case 'config': {
      // O painel informa o endereço da API em uso.
      const {api} = message.payload || {};
      if (api) await setConfig({apiBase: api});
      if (sender.origin) await setConfig({panelUrl: sender.origin});
      return {saved: true};
    }
    case 'setAutoSend': {
      const {enabled, intervalSeconds} = message.payload || {};
      await setConfig({autoSend: Boolean(enabled), ...(intervalSeconds ? {sendIntervalSeconds: Number(intervalSeconds)} : {})});
      await ensureAlarm();
      if (enabled) processQueueOnce();
      return status();
    }
    case 'token': {
      // O painel informa o login atual; o botão e a fila usam esse acesso.
      const {token} = message.payload || {};
      if (token) await chrome.storage.local.set({apiToken: token});
      else await chrome.storage.local.remove('apiToken');
      return {saved: Boolean(token)};
    }
    default: throw new Error('Comando desconhecido.');
  }
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  const allowed = sender.id === chrome.runtime.id && (sender.url || '').match(/^http:\/\/(localhost|127\.0\.0\.1):5173\//);
  if (!allowed) { reply({ok: false, error: 'Origem não autorizada.'}); return false; }
  handle(message, sender).then(
    result => reply({ok: true, result}),
    error => { console.info('[Autopost] erro em', message.type, error); reply({ok: false, error: error.message || String(error)}); },
  );
  return true; // resposta assíncrona
});
