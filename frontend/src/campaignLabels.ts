type Color = 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning';
export const campaignStatus: Record<string, [string, Color]> = {
  draft: ['Rascunho', 'default'], scheduled: ['Aguardando execução', 'info'], running: ['Em execução', 'primary'],
  paused: ['Pausada', 'warning'], completed: ['Concluída', 'success'], completed_with_failures: ['Concluída com falhas', 'warning'],
  failed: ['Falhou', 'error'], cancelled: ['Cancelada', 'default'],
};
export const strategyLabel: Record<string, [string, string]> = {
  balanced: ['Equilibrada', 'Cada produto vai para um grupo, alternando para que todos recebam quantidades parecidas.'],
  sequential: ['Sequencial', 'Um produto por vez, enviado para todos os grupos selecionados.'],
  category: ['Por categoria', 'Cada grupo recebe só os produtos das categorias definidas no cadastro do grupo.'],
  custom: ['Personalizada', 'Você escolhe aqui, para cada grupo, quais categorias oficiais (ou categorias e tags antigas) ele recebe.'],
};
export const WEEKDAYS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'];
export const dateTime = (iso: string | null) => iso ? new Date(iso).toLocaleString('pt-BR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'}) : '';
export function duration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60), m = minutes % 60;
  if (h < 48) return m ? `${h} h ${m} min` : `${h} h`;
  return `${Math.round(h / 24)} dias`;
}
export function rhythm(c: {block_size: number; interval_minutes: number; interval_max_minutes: number; message_gap_seconds?: number}): string {
  const n = c.block_size === 1 ? '1 anúncio' : `${c.block_size} anúncios (${c.message_gap_seconds || 20} s entre eles)`;
  const every = c.interval_max_minutes > c.interval_minutes ? `entre ${c.interval_minutes} e ${c.interval_max_minutes} min` : `${c.interval_minutes} min`;
  return `${n} a cada ${every}`;
}
