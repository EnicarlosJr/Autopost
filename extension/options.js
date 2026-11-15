import {getConfig, setConfig} from './config.js';
const $ = id => document.getElementById(id);

async function load() {
  const config = await getConfig();
  const {apiToken, queueStatus} = await chrome.storage.local.get(['apiToken', 'queueStatus']);
  $('autoSend').checked = config.autoSend;
  $('interval').value = config.sendIntervalSeconds;
  $('apiBase').value = config.apiBase;
  $('state').textContent = `${apiToken ? 'Conectado ao painel.' : 'Sem login: abra o painel e entre.'}${queueStatus ? ` Última atividade da fila: ${queueStatus.text}` : ''}`;
}

$('save').onclick = async () => {
  await setConfig({autoSend: $('autoSend').checked, sendIntervalSeconds: Number($('interval').value), apiBase: $('apiBase').value.trim()});
  $('result').textContent = 'Opções salvas.'; $('result').hidden = false;
  load();
};
load();
