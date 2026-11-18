// Chamadas à API do Autopost com o login copiado do painel.
import {getConfig} from './config.js';

export class ApiError extends Error {
  constructor(message, status, detail) { super(message); this.status = status; this.detail = detail; }
}

export async function hasToken() {
  const {apiToken} = await chrome.storage.local.get('apiToken');
  return Boolean(apiToken);
}

/** Baixa um arquivo da API (ex.: a foto padronizada) e devolve em base64, para passar à aba do WhatsApp. */
export async function apiBase64(path) {
  const [{apiBase}, {apiToken}] = await Promise.all([getConfig(), chrome.storage.local.get('apiToken')]);
  const response = await fetch(`${apiBase}${path}`, {headers: {Authorization: `Bearer ${apiToken}`}}).catch(() => null);
  if (!response) throw new ApiError('Não consegui falar com o Autopost para baixar a foto.', 0);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(typeof data.detail === 'string' ? data.detail : `Não consegui gerar a foto (${response.status}).`, response.status);
  }
  const bytes = new Uint8Array(await response.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

export async function api(path, {method = 'GET', body} = {}) {
  const [{apiBase}, {apiToken}] = await Promise.all([getConfig(), chrome.storage.local.get('apiToken')]);
  if (!apiToken) throw new ApiError('Abra o painel do Autopost neste Chrome e faça login.', 401);
  let response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      method,
      headers: {Authorization: `Bearer ${apiToken}`, ...(body ? {'Content-Type': 'application/json'} : {})},
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError('Não consegui falar com o Autopost. Confira se ele está rodando (docker compose up -d).', 0);
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    await chrome.storage.local.remove('apiToken');
    throw new ApiError('Seu login no painel expirou. Abra o Autopost e entre de novo.', 401);
  }
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || detail?.[0]?.msg || `O Autopost recusou o pedido (${response.status}).`;
    throw new ApiError(message, response.status, detail);
  }
  return data;
}
