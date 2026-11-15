// Ponte entre o painel do Autopost (localhost:5173) e a extensão.
// Só repassa mensagens da própria página; nada de outros sites chega aqui.
(() => {
  let VERSION = '?';
  try { VERSION = chrome.runtime.getManifest().version; } catch { /* extensão recarregada */ }
  const reply = message => window.postMessage({source: 'autopost-extension', ...message}, location.origin);
  const announce = () => reply({type: 'ready', version: VERSION});

  window.addEventListener('message', event => {
    if (event.source !== window || event.origin !== location.origin) return;
    const data = event.data;
    if (!data || data.source !== 'autopost-page' || !data.id) return;
    if (data.type === 'hello') { announce(); return; }
    try {
      chrome.runtime.sendMessage({type: data.type, payload: data.payload}, response => {
        const error = chrome.runtime.lastError?.message;
        reply({id: data.id, ok: !error && response?.ok !== false, result: response?.result, error: error || response?.error});
      });
    } catch {
      // A extensão foi recarregada e esta página ainda usa a ponte antiga.
      reply({id: data.id, ok: false, error: 'A extensão foi atualizada. Aperte F5 nesta página e tente de novo.'});
    }
  });

  // Repassa o login do painel para a extensão (usado pelo botão "Cadastrar no Autopost").
  let lastToken;
  const syncToken = () => {
    let token = null;
    try { token = localStorage.getItem('autopost_token'); } catch { /* sem acesso */ }
    if (token === lastToken) return;
    lastToken = token;
    try { chrome.runtime.sendMessage({type: 'token', payload: {token}}); } catch { /* extensão recarregada */ }
  };
  syncToken();
  setInterval(syncToken, 3000);

  announce();
})();
