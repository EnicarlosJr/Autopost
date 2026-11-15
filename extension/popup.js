// Janela do botão da extensão: lê o produto da aba atual e cadastra no Autopost (opcionalmente já na fila).
import {api, hasToken} from './api.js';
import {getConfig} from './config.js';

const $ = id => document.getElementById(id);
let captured = null;

const money = n => n.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
const setStatus = (text, error = false) => { $('status').textContent = text; $('status').classList.toggle('error', error); $('status').hidden = !text; };
const showResult = (text, error = false) => { $('result').textContent = text; $('result').classList.toggle('error', error); $('result').hidden = false; };

function marketplaceFrom(url, store) {
  const host = new URL(url).hostname;
  if (/mercadoli(vre|bre)/.test(host)) return 'Mercado Livre';
  if (/amazon/.test(host)) return 'Amazon';
  if (/magazineluiza|magalu/.test(host)) return 'Magalu';
  if (/shopee/.test(host)) return 'Shopee';
  return store || host.replace(/^www\./, '');
}

function render(data) {
  $('title').textContent = data.title || 'Produto sem nome';
  $('image').onerror = () => { $('image').hidden = true; };
  if (data.image_url) $('image').src = data.image_url; else $('image').hidden = true;
  const hasOld = data.original_price != null && data.price != null && data.original_price > data.price;
  $('old').hidden = !hasOld;
  if (hasOld) $('old').textContent = `De ${money(data.original_price)}`;
  $('price').textContent = data.price != null ? `Por ${money(data.price)}` : 'Preço não encontrado';
  const tag = (cls, text) => { const span = document.createElement('span'); span.className = cls; span.textContent = text; $('price').append(span); };
  if (data.price != null && data.price_note) tag('note', data.price_note);
  if (hasOld) tag('off', `−${Math.floor((data.original_price - data.price) / data.original_price * 100)}%`);
  $('product').hidden = false;
}

async function submit(enqueue) {
  const affiliate = $('affiliate').value.trim();
  const group = $('group').value.trim();
  if (affiliate && !/^https?:\/\//i.test(affiliate)) { showResult('O link de afiliado precisa começar com https://', true); return; }
  if (enqueue && !group) { showResult('Informe o nome exato do grupo para pôr na fila.', true); return; }
  for (const id of ['save', 'enqueue']) $(id).disabled = true;
  $('result').hidden = true;
  try {
    const body = {...captured, original_url: captured.canonical_url || captured.page_url, affiliate_url: affiliate || null,
                  category: $('category').value.trim(), marketplace: $('marketplace').value.trim(), enqueue, group_name: group};
    delete body.canonical_url; delete body.page_url; delete body.blocked;
    const data = await api('/products/from-browser', {method: 'POST', body});
    await chrome.storage.local.set({lastCategory: body.category, lastGroup: group || (await chrome.storage.local.get('lastGroup')).lastGroup || ''});
    let text = data.created ? 'Produto cadastrado no Autopost.' : 'Este produto já existia; os dados foram atualizados.';
    if (enqueue) text += data.publication_id ? ` Publicação na fila para "${group}".` : ' Já existe uma publicação ativa ou recente dele para este grupo; nada novo foi para a fila.';
    showResult(text);
  } catch (error) {
    showResult(error.message, true);
    for (const id of ['save', 'enqueue']) $(id).disabled = false;
  }
}

async function init() {
  const {panelUrl} = await getConfig();
  const {lastCategory = '', lastGroup = ''} = await chrome.storage.local.get(['lastCategory', 'lastGroup']);
  $('panel').onclick = event => { event.preventDefault(); chrome.tabs.create({url: `${panelUrl}/products`}); };
  if (!await hasToken()) { setStatus('Abra o painel do Autopost neste Chrome e faça login. Depois clique aqui de novo.', true); return; }
  // ?tab=<id> permite abrir esta janela como página (usado em testes); normalmente é a aba ativa.
  const forced = Number(new URLSearchParams(location.search).get('tab'));
  const [tab] = forced ? [await chrome.tabs.get(forced)] : await chrome.tabs.query({active: true, currentWindow: true});
  if (!tab || !/^https?:/.test(tab.url || '')) { setStatus('Abra a página de um produto e clique no botão de novo.', true); return; }
  try {
    const [injection] = await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['reader.js']});
    captured = injection?.result;
  } catch {
    setStatus('Não consegui ler esta página. Confira se a extensão tem acesso a este site (Detalhes > Acesso ao site).', true);
    return;
  }
  if (!captured || captured.blocked) { setStatus('A loja pediu login ou verificação. Abra o produto normalmente e tente de novo.', true); return; }
  if (!captured.title && captured.price == null) { setStatus('Esta página não parece ser de um produto.', true); return; }
  setStatus('');
  $('category').value = lastCategory;
  $('group').value = lastGroup;
  $('marketplace').value = marketplaceFrom(captured.canonical_url || captured.page_url, captured.store);
  render(captured);
  $('save').onclick = () => submit(false);
  $('enqueue').onclick = () => submit(true);
  // O grupo padrão das Configurações, quando não houver um usado antes.
  if (!lastGroup) api('/automations/settings').then(s => { if (!$('group').value) $('group').value = s.whatsapp_group_name || ''; }).catch(() => {});
}

init();
