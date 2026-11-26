// Configuração da extensão (guardada no navegador). O painel informa o endereço da API ao abrir.
export const DEFAULTS = {
  apiBase: 'http://localhost:8000/api',
  panelUrl: 'http://localhost:5173',
  // Painel de produção (https://painel.seudominio...): só muda pelas Opções da extensão, com a sua permissão.
  remotePanel: '',
  autoSend: false,          // envio automático da fila, mesmo com o painel fechado
  sendIntervalSeconds: 60,  // intervalo entre mensagens da fila
};
export const MIN_INTERVAL_SECONDS = 20; // trava de segurança entre duas mensagens quaisquer

export async function getConfig() {
  const stored = await chrome.storage.local.get(Object.keys(DEFAULTS));
  return {...DEFAULTS, ...stored};
}

export async function setConfig(values) {
  const clean = {};
  if (typeof values.apiBase === 'string' && /^https?:\/\//.test(values.apiBase)) clean.apiBase = values.apiBase.replace(/\/+$/, '');
  if (typeof values.panelUrl === 'string' && /^https?:\/\//.test(values.panelUrl)) clean.panelUrl = values.panelUrl.replace(/\/+$/, '');
  if (typeof values.remotePanel === 'string' && (values.remotePanel === '' || /^https:\/\/[^/]+$/.test(values.remotePanel))) clean.remotePanel = values.remotePanel;
  if (typeof values.autoSend === 'boolean') clean.autoSend = values.autoSend;
  if (Number.isFinite(values.sendIntervalSeconds)) clean.sendIntervalSeconds = Math.max(MIN_INTERVAL_SECONDS, Math.round(values.sendIntervalSeconds));
  await chrome.storage.local.set(clean);
  return getConfig();
}

/** Origem que pode mandar comandos: o painel local (localhost:5173) ou o painel de produção liberado nas Opções. */
export async function isAllowedPanel(url) {
  if (/^http:\/\/(localhost|127\.0\.0\.1):5173\//.test(url || '')) return true;
  const {remotePanel} = await getConfig();
  return Boolean(remotePanel) && (url || '').startsWith(`${remotePanel}/`);
}

export const log = (...args) => console.info('[Autopost]', ...args);
export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
