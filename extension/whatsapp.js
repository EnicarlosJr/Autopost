// Envio pela aba do WhatsApp Web que o usuário já tem aberta.
// Todos os seletores do WhatsApp ficam em sendInWhatsApp (abaixo): quando o site mudar, é o único lugar a ajustar.
import {MIN_INTERVAL_SECONDS} from './config.js';

let busy = false;

async function lastSentAt() {
  const {lastSentAt = 0} = await chrome.storage.local.get('lastSentAt');
  return lastSentAt;
}

export async function nextSendIn(intervalSeconds = MIN_INTERVAL_SECONDS) {
  const wait = Math.max(intervalSeconds, MIN_INTERVAL_SECONDS) * 1000;
  return Math.max(0, Math.ceil((await lastSentAt() + wait - Date.now()) / 1000));
}

export function isSending() { return busy; }

export async function whatsappTab() {
  const tabs = await chrome.tabs.query({url: 'https://web.whatsapp.com/*'});
  return tabs.find(t => t.active) || tabs[0] || null;
}

export async function sendToWhatsApp({group, message, useOpenChat = false}) {
  group = (group || '').trim(); message = (message || '').trim();
  if (!group || !message) throw new Error('Selecione um grupo e uma mensagem não vazia.');
  if (busy) throw new Error('Outro envio já está em andamento.');
  const wait = await nextSendIn();
  if (wait > 0) throw new Error(`Aguarde ${wait} s antes do próximo envio.`);
  const tab = await whatsappTab();
  if (!tab) throw new Error('Abra o WhatsApp Web (web.whatsapp.com) em uma aba deste navegador.');
  if (tab.discarded) throw new Error('A aba do WhatsApp Web foi suspensa pelo navegador. Clique nela para recarregar e tente de novo.');

  busy = true;
  const [previous] = await chrome.tabs.query({active: true, windowId: tab.windowId});
  // Janela minimizada ou coberta deixa a página "oculta": o Chrome desacelera o WhatsApp e a
  // prévia do link (foto e título) não é montada. Durante o envio a janela fica visível e na frente.
  const win = await chrome.windows.get(tab.windowId).catch(() => null);
  const lastFocused = await chrome.windows.getLastFocused().catch(() => null);
  try {
    if (win?.state === 'minimized') await chrome.windows.update(win.id, {state: 'normal'});
    if (win) await chrome.windows.update(win.id, {focused: true}).catch(() => {});
    if (!tab.active) await chrome.tabs.update(tab.id, {active: true});
    await new Promise(resolve => setTimeout(resolve, 1500));   // máquinas mais lentas precisam de um respiro para redesenhar
    const [injection] = await chrome.scripting.executeScript({
      target: {tabId: tab.id},
      func: sendInWhatsApp,
      args: [group, message, Boolean(useOpenChat)],
    });
    const result = injection?.result;
    if (!result?.ok) {
      const error = new Error(result?.error || 'O WhatsApp Web não respondeu ao envio.');
      error.code = result?.code || '';
      throw error;
    }
    await chrome.storage.local.set({lastSentAt: Date.now()});
    return {sent: true, confirmed: Boolean(result.confirmed), group, preview: result.preview || ''};
  } finally {
    busy = false;
    if (previous && previous.id !== tab.id) chrome.tabs.update(previous.id, {active: true}).catch(() => {});
    if (win?.state === 'minimized') chrome.windows.update(win.id, {state: 'minimized'}).catch(() => {});
    else if (lastFocused && win && lastFocused.id !== win.id) chrome.windows.update(lastFocused.id, {focused: true}).catch(() => {});
  }
}

// ---------------------------------------------------------------------------
// Executada DENTRO da aba do WhatsApp Web. Precisa ser autocontida (sem imports).
// ---------------------------------------------------------------------------
async function sendInWhatsApp(group, message, useOpenChat, dryRun = false) {
  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = el => Boolean(el) && el.getClientRects().length > 0;
  // Ignora maiúsculas, espaços repetidos e caracteres invisíveis (comuns em nomes com emoji).
  const norm = s => (s || '').normalize('NFC').replace(/[\u200B-\u200F\u202A-\u202E\u2060\uFE0E\uFE0F\u00A0]/g, ' ')
    .replace(/\s+/g, ' ').trim().toLocaleLowerCase();
  const waitFor = async (check, timeout, error) => {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      try { const value = check(); if (value) return value; } catch { /* tenta de novo */ }
      await sleep(250);
    }
    throw new Error(error);
  };
  const textOf = el => (el?.tagName === 'INPUT' ? el.value : el?.innerText) || '';
  const clearField = el => {
    el.focus();
    if (el.tagName === 'INPUT') return;
    if (!textOf(el).trim()) return;
    // O editor do WhatsApp (Lexical) só apaga quando recebe o evento "beforeinput" com a seleção
    // cobrindo todo o conteúdo. execCommand fica como reserva para outros campos.
    const selection = getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    selection.removeAllRanges(); selection.addRange(range);
    el.dispatchEvent(new InputEvent('beforeinput', {inputType: 'deleteContentBackward', bubbles: true, cancelable: true}));
    if (textOf(el).trim()) {
      selection.removeAllRanges(); selection.addRange(range);
      document.execCommand('delete', false);
    }
  };
  const pasteData = (el, data) => {
    el.focus();
    el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true}));
  };
  const setText = async (el, text) => {
    if (el.tagName === 'INPUT') {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      el.focus(); setter.call(el, text);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      return;
    }
    clearField(el);
    await sleep(150);
    if (textOf(el).trim()) throw new Error('Não consegui limpar a caixa de mensagem do WhatsApp (havia um rascunho). Apague o texto da conversa e tente de novo.');
    // Somente texto simples: sem HTML nem imagem na área de transferência.
    const data = new DataTransfer(); data.setData('text/plain', text);
    pasteData(el, data);
    // Em máquinas lentas o WhatsApp demora para processar a colagem: espera até 3 s antes do plano B.
    const probe = norm(text.split('\n').find(line => line.trim()) || text).slice(0, 25);
    for (let end = Date.now() + 3000; Date.now() < end && !norm(textOf(el)).includes(probe);) await sleep(200);
    if (!norm(textOf(el)).includes(probe)) {
      clearField(el);
      document.execCommand('insertText', false, text);
      await sleep(300);
    }
  };
  const click = el => {
    for (const type of ['mousedown', 'mouseup', 'click']) {
      el.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, view: window}));
    }
  };
  const label = el => `${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''} ${el.getAttribute('data-icon') || ''}`;
  const sendButton = scope => {
    const icons = [...scope.querySelectorAll('[data-icon="send"], [data-icon="wds-ic-send-filled"], [data-icon*="send"]')].filter(visible);
    const fromIcon = icons.map(i => i.closest('button,[role="button"]') || i).pop();
    return fromIcon || [...scope.querySelectorAll('button,[role="button"]')].filter(visible).filter(b => /\b(send|enviar)\b/i.test(label(b))).pop();
  };
  // Mensagens na conversa que contêm um trecho do texto enviado (o link da oferta ou a 1ª linha).
  // O WhatsApp atual não usa mais a classe .message-out; o data-testid msg-container é o atual.
  const probeOf = text => (text.match(/https?:\/\/[^\s]+/) || [])[0] || norm(text.split('\n').find(l => l.trim()) || '').slice(0, 40);
  const bubbles = () => [...document.querySelectorAll('#main [data-testid="msg-container"], #main .message-out, #main [data-id]')]
    .filter(el => !el.parentElement?.closest('[data-testid="msg-container"], .message-out'));
  const countWith = probe => bubbles().filter(el => (el.innerText || el.textContent || '').includes(probe) || norm(el.innerText || '').includes(probe)).length;

  try {
    await waitFor(() => document.querySelector('#pane-side') || document.querySelector('#side'), 30000,
      'O WhatsApp Web não está carregado. Abra a aba e leia o QR Code se for preciso.');

    const target = norm(group);
    const nameOf = el => el.getAttribute('title') || el.textContent || '';
    // Nomes de conversas visíveis fora da conversa aberta (lista lateral e resultados de busca).
    const chatNames = () => [...document.querySelectorAll('span[title], span[dir="auto"], div[title]')]
      .filter(e => visible(e) && !e.closest('#main') && !e.closest('footer') && nameOf(e).trim().length > 0 && nameOf(e).length < 120);
    const findRow = () => {
      const match = chatNames().find(e => norm(nameOf(e)) === target);
      return match && (match.closest('[role="listitem"], [role="row"], [role="gridcell"], [tabindex]') || match);
    };
    const headerName = () => {
      const header = document.querySelector('#main header');
      if (!header) return '';
      const names = [...header.querySelectorAll('span[title], span[dir="auto"], div[title]')].map(nameOf).filter(t => t.trim());
      return names.find(t => norm(t) === target) || names[0] || '';
    };
    const isTargetOpen = () => norm(headerName()) === target;

    if (useOpenChat) {
      // 1. Modo "conversa aberta": não busca nada, só confere o nome no topo da conversa.
      if (!document.querySelector('#main header')) throw new Error('Nenhuma conversa está aberta no WhatsApp Web. Abra o grupo e tente de novo.');
      if (!isTargetOpen()) throw new Error(`A conversa aberta é "${headerName() || 'desconhecida'}", não "${group}". Nada foi enviado.`);
    } else if (!isTargetOpen()) {
      // 1. Procura o grupo primeiro na lista visível; se não estiver, usa a busca.
      let row = findRow();
      if (!row) {
        const side = document.querySelector('#side') || document.body;
        const searchCandidates = () => [
          ...side.querySelectorAll('[data-tab="3"][contenteditable="true"], input[role="textbox"], input[type="text"], [contenteditable="true"][role="textbox"], div[contenteditable="true"]'),
          ...document.querySelectorAll('input[aria-label*="esquis"], input[aria-label*="earch"], [contenteditable="true"][aria-label*="esquis"], [contenteditable="true"][aria-label*="earch"]'),
        ].filter(e => visible(e) && !e.closest('#main'));
        let search = searchCandidates()[0];
        if (!search) {
          const button = [...document.querySelectorAll('button,[role="button"]')].find(b => visible(b) && /search|pesquis/i.test(label(b)));
          if (button) click(button);
          search = await waitFor(() => searchCandidates()[0], 8000, 'Não encontrei a busca de conversas do WhatsApp.');
        }
        await setText(search, group);
        row = await waitFor(findRow, 15000, '').catch(() => null);
        if (!row) {
          const seen = [...new Set(chatNames().map(e => nameOf(e).trim()))].slice(0, 12);
          throw new Error(`Não encontrei a conversa "${group}". Nomes que apareceram: ${seen.length ? seen.map(n => `"${n}"`).join(', ') : 'nenhum'}. Confira o nome do grupo na publicação ou use "Enviar para a conversa aberta".`);
        }
      }
      click(row);
      // 2. Confere que a conversa aberta é mesmo o grupo (evita mandar para a conversa errada).
      await waitFor(isTargetOpen, 10000, '').catch(() => {
        throw new Error(`A conversa aberta é "${headerName() || 'desconhecida'}", não "${group}". Nada foi enviado.`);
      });
    }
    const composer = await waitFor(() => [...document.querySelectorAll('#main footer div[contenteditable="true"]')].find(visible),
      10000, 'Não encontrei a caixa de mensagem da conversa.');

    // 3. Somente texto, colado como um Ctrl+V: o WhatsApp aplica a formatação
    // (*negrito*, _itálico_, ~riscado~) e monta a prévia do link sozinho.
    const footer = document.querySelector('#main footer') || document.body;
    const footerText = () => {
      const clone = footer.cloneNode(true);
      clone.querySelectorAll('div[contenteditable="true"], button, [role="button"]').forEach(el => el.remove());
      return (clone.textContent || '').replace(/\s+/g, ' ').trim();
    };
    const baseText = footerText();   // textos fixos do rodapé (ex.: "Digite uma mensagem")
    await setText(composer, message);
    let preview = 'sem link';
    if (/https?:\/\//i.test(message)) {
      // Espera a prévia do link ficar completa antes de enviar. O WhatsApp mostra primeiro
      // um cartão provisório só com o domínio (ex.: "meli.la") e, depois de seguir o link
      // curto até a loja, completa com título e foto. Enviar antes manda o cartão vazio.
      const links = message.match(/https?:\/\/[^\s]+/g) || [];
      const hosts = links.map(l => { try { return new URL(l).hostname.replace(/^www\./, ''); } catch { return ''; } }).filter(Boolean);
      // Cartão da prévia montado acima da caixa de mensagem (identificadores atuais do WhatsApp Web).
      const previewBox = () => document.querySelector('#main [data-testid="compose-box-link-preview"]');
      const cardImage = () => {
        const box = previewBox();
        const scope = box ? [...box.querySelectorAll('img')] : [...footer.querySelectorAll('img')];
        return scope.find(img => visible(img) && !composer.contains(img) && img.complete && img.naturalWidth >= 50
          && img.naturalHeight >= 50 && !/emoji/i.test(img.className));
      };
      // Texto do cartão (fora da caixa de mensagem), sem os textos fixos, o link e o domínio.
      // Cartão provisório: título vazio, só o domínio ("meli.la") ou o próprio link. Acontece enquanto o
      // WhatsApp ainda segue o link curto e também quando o link acabou de ser criado e a leitura falhou.
      const provisional = title => !title || hosts.some(h => title === h) || /https?:\/\/|^[\w.-]+\.[a-z]{2,}(\/\S*)?$/i.test(title)
        || links.some(l => title.includes(l) || l.includes(title));
      const cardText = () => {
        const title = previewBox()?.querySelector('[data-testid="link-preview-title"]')?.textContent?.trim();
        if (title) return provisional(title) ? '' : title;
        let text = ' ' + footerText() + ' ';
        for (const piece of [...baseText.split(' ').filter(w => w.length > 2), ...links, ...hosts]) text = text.split(piece).join(' ');
        return text.replace(/\s+/g, ' ').trim();
      };
      let hiddenSeen = false;
      // Até 3 tentativas: se o cartão continuar provisório, apaga e cola de novo para o WhatsApp reler o link.
      for (let attempt = 1; attempt <= 3 && preview === 'sem link'; attempt++) {
        if (attempt > 1) {
          clearField(composer);
          await sleep(2500 * attempt);
          await setText(composer, message);
        }
        const start = Date.now();
        let titledSince = 0;
        while (Date.now() - start < 30000) {
          if (document.visibilityState === 'hidden') hiddenSeen = true;
          if (cardImage() && cardText().length > 3) { preview = 'com imagem'; await sleep(800); break; }
          if (cardText().length > 3) {
            // Já tem título de verdade mas ainda sem foto: dá mais alguns segundos para a foto chegar.
            titledSince ||= Date.now();
            if (Date.now() - titledSince > 15000) { preview = 'sem imagem (a loja não enviou foto)'; break; }
          }
          await sleep(300);
        }
      }
      if (preview === 'sem link') {
        // Sem prévia de verdade: não envia. A publicação volta para a fila e é tentada de novo mais tarde.
        clearField(composer);
        const why = hiddenSeen
          ? ' A tela do WhatsApp ficou oculta durante a espera (Chrome minimizado, computador bloqueado ou tela desligada), e assim o WhatsApp não monta a prévia. Deixe o computador desbloqueado com a tela ligada.'
          : ` O cartão ficou: "${cardText() || previewBox()?.innerText?.trim().slice(0, 60) || 'vazio'}".`;
        return {ok: false, code: 'no_preview', error: 'O WhatsApp não montou a prévia do link (foto e título) depois de 3 tentativas. Nada foi enviado.' + why};
      }
    }
    const probe = probeOf(message);
    const before = countWith(probe);
    if (dryRun) {
      // Validação sem enviar: devolve o que seria enviado e limpa a caixa.
      const result = {ok: true, dryRun: true, preview, composer: textOf(composer), probe, before};
      clearField(composer);
      return result;
    }
    // Confere se a caixa tem a mensagem inteira (com o link) antes de enviar.
    const typed = textOf(composer);
    const linkInMessage = (message.match(/https?:\/\/[^\s]+/) || [])[0];
    if (linkInMessage && !typed.includes(linkInMessage)) {
      clearField(composer);
      return {ok: false, code: 'bad_text', error: 'A mensagem não foi colada inteira na caixa do WhatsApp (o link ficou de fora). Nada foi enviado.'};
    }
    const button = sendButton(footer);
    if (button) click(button);
    else composer.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));

    // 4. Confirmação: a caixa esvaziou e/ou apareceu a nova mensagem na conversa (até 40 s em máquinas lentas).
    let cleared = false, confirmed = false;
    for (let end = Date.now() + 40000; Date.now() < end && !(cleared && confirmed);) {
      cleared = !textOf(composer).trim();
      confirmed = countWith(probe) > before;
      if (confirmed && !cleared) await sleep(1000);       // saiu, só falta a caixa limpar
      else await sleep(400);
    }
    if (!cleared && !confirmed) {
      return {ok: false, code: 'unconfirmed', error: 'Cliquei em enviar, mas o WhatsApp não confirmou em 40 s. Confira no grupo se a mensagem saiu antes de reenviar.'};
    }
    return {ok: true, confirmed, preview};
  } catch (error) {
    return {ok: false, error: error?.message || String(error)};
  }
}

// Exposta só para os testes de ponta a ponta (tests_e2e).
export const __test_sendInWhatsApp = sendInWhatsApp;
