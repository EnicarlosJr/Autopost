type Color = 'default'|'primary'|'secondary'|'error'|'info'|'success'|'warning';

const productStatus: Record<string,[string,Color]> = {
  pending:['Aguardando','default'], processing:['Extraindo…','info'], awaiting_browser:['Aguardando navegador','warning'],
  processed:['Pronto','success'], needs_review:['Revisar','warning'], error:['Erro','error'],
};
const publicationStatus: Record<string,[string,Color]> = {
  pending:['Aguardando aprovação','warning'], awaiting_approval:['Aguardando aprovação','warning'],
  approved:['Pronta','primary'], scheduled:['Agendada','info'], paused:['Pausada','warning'], sending:['Enviando…','info'],
  sent:['Enviada','success'], failed:['Falhou','error'], cancelled:['Cancelada','default'],
};

export const productLabel = (s:string) => productStatus[s] ?? [s,'default'];
export const publicationLabel = (s:string) => publicationStatus[s] ?? [s,'default'];
export const productStatuses = Object.keys(productStatus);

export const money = (n:number) => n.toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
export const discount = (price:number|null, original:number|null) =>
  price!=null && original!=null && original>price ? Math.floor((original-price)*100/original) : null;

/** Lojas que bloqueiam o servidor: os dados vêm da leitura pelo navegador. */
export const needsBrowser = (url:string) => /(^|\.)(mercadolivre\.com(\.br)?|mercadolibre\.com|meli\.la)$/i.test((()=>{try{return new URL(url).hostname}catch{return ''}})());

export function timeAgo(iso:string|null): string {
  if (!iso) return 'nunca';
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return 'agora';
  if (minutes < 60) return `há ${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `há ${hours} h` : `há ${Math.round(hours / 24)} dias`;
}

/** Converte ISO para o valor aceito por <input type="datetime-local"> no fuso local. */
export function toLocalInput(iso:string|null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n:number) => String(n).padStart(2,'0');
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
