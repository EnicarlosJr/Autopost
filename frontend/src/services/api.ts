import axios from 'axios';

export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
export const api = axios.create({baseURL: API_BASE});

api.interceptors.request.use(config => {
  const token = localStorage.getItem('autopost_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(response => response, error => {
  if (error.response?.status === 401 && !error.config?.url?.includes('/auth/')) {
    localStorage.removeItem('autopost_token');
    window.location.reload();
  }
  return Promise.reject(error);
});

/** Extrai a mensagem de erro da API (ou de um Error comum) para exibir na tela. */
export function apiError(error: unknown, fallback: string): string {
  const e = error as {response?: {data?: {detail?: unknown}}; message?: string};
  const detail = e?.response?.data?.detail as any;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return String(detail.message);
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  if (e?.message === 'Network Error') return 'Não consegui falar com o Autopost. Confira se ele está rodando.';
  return e?.message && !e.message.startsWith('Request failed') ? e.message : fallback;
}

/** Página de uma lista com o total vindo do cabeçalho X-Total-Count. */
export async function getPage<T>(url: string, params: Record<string, unknown>): Promise<{items: T[]; total: number}> {
  const response = await api.get<T[]>(url, {params});
  return {items: response.data, total: Number(response.headers['x-total-count'] ?? response.data.length)};
}
