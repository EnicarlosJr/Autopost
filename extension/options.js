import {getConfig, setConfig} from './config.js';
const $ = id => document.getElementById(id);

async function load() {
  const config = await getConfig();
  const {apiToken, queueStatus} = await chrome.storage.local.get(['apiToken', 'queueStatus']);
  $('autoSend').checked = config.autoSend;
  $('interval').value = config.sendIntervalSeconds;
  $('apiBase').value = config.apiBase;
  $('remotePanel').value = config.remotePanel;
  $('state').textContent = `${apiToken ? 'Conectado ao painel.' : 'Sem login: abra o painel e entre.'}${queueStatus ? ` Última atividade da fila: ${queueStatus.text}` : ''}`;
}

const BRIDGE_ID = 'autopost-bridge-remote';

/** Libera o painel de produção: pede permissão ao Chrome e liga a ponte só nesse endereço. */
async function applyRemotePanel(value) {
  const previous = (await getConfig()).remotePanel;
  await chrome.scripting.unregisterContentScripts({ids: [BRIDGE_ID]}).catch(() => {});
  if (previous && previous !== value) await chrome.permissions.remove({origins: [`${previous}/*`]}).catch(() => {});
  if (!value) return {remotePanel: ''};
  const origin = new URL(value).origin;
  if (!origin.startsWith('https://')) throw new Error('Use o endereço com https://.');
  const granted = await chrome.permissions.request({origins: [`${origin}/*`]});
  if (!granted) throw new Error('Sem a permissão do Chrome, a extensão não funciona no painel online.');
  await chrome.scripting.registerContentScripts([{id: BRIDGE_ID, matches: [`${origin}/*`], js: ['bridge.js'], runAt: 'document_start'}]);
  return {remotePanel: origin, apiBase: `${origin}/api`, panelUrl: origin};
}

$('save').onclick = async () => {
  try {
    const remote = await applyRemotePanel($('remotePanel').value.trim());
    await setConfig({autoSend: $('autoSend').checked, sendIntervalSeconds: Number($('interval').value), apiBase: $('apiBase').value.trim(), ...remote});
    $('result').textContent = remote.remotePanel ? `Opções salvas. Abra ${remote.remotePanel} e faça login.` : 'Opções salvas.';
  } catch (error) {
    $('result').textContent = error.message || String(error);
  }
  $('result').hidden = false;
  load();
};
load();
