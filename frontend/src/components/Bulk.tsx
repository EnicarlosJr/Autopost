import {useState, type ReactNode} from 'react';
import {Alert, Autocomplete, Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton,
  Stack, TextField, Tooltip, Typography} from '@mui/material';
import {getPage} from '../services/api';
import {CloseIcon, UnfoldLessIcon, UnfoldMoreIcon} from './Icons';
import {tokens} from '../theme';

/** Seleção de itens de uma lista: marcar um, todos da página e limpar. */
export function useSelection() {
  const [ids, setIds] = useState<number[]>([]);
  return {
    ids, count: ids.length,
    has: (id: number) => ids.includes(id),
    toggle: (id: number) => setIds(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id]),
    setAll: (all: number[]) => setIds(all),
    add: (more: number[]) => setIds(old => [...new Set([...old, ...more])]),
    clear: () => setIds([]),
  };
}

/** Caixa "Selecionar todos" com estado parcial. */
export function SelectAll({total, selected, onAll, onNone, label = 'Selecionar todos'}: {total: number; selected: number; onAll: () => void; onNone: () => void; label?: string}) {
  return <FormControlLabel sx={{mr: 1}} label={selected ? `${selected} selecionado(s)` : label}
    control={<Checkbox checked={total > 0 && selected === total} indeterminate={selected > 0 && selected < total}
      disabled={!total} onChange={() => (selected === total ? onNone() : onAll())}/>}/>;
}

/** Barra de ações que aparece presa ao rodapé enquanto há itens selecionados. */
export function BulkBar({count, noun, onClear, children}: {count: number; noun: string; onClear: () => void; children: ReactNode}) {
  if (!count) return null;
  return <Box role="region" aria-label="Ações para os itens selecionados" sx={{
    position: 'sticky', bottom: 16, zIndex: 20, mt: 2, mx: 'auto', maxWidth: 900, bgcolor: tokens.ink, color: '#fff', borderRadius: 3,
    px: 2, py: 1.25, display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', boxShadow: '0 10px 30px rgba(26,33,64,.28)'}}>
    <Typography fontWeight={700} sx={{mr: 1}}>{count} {noun}</Typography>
    <Stack direction="row" gap={.75} flexWrap="wrap" flex={1} sx={{'& .MuiButton-root': {color: '#fff', borderColor: 'rgba(255,255,255,.3)'}}}>{children}</Stack>
    <Tooltip title="Limpar seleção"><IconButton aria-label="Limpar seleção" onClick={onClear} sx={{color: '#fff'}}><CloseIcon fontSize="small"/></IconButton></Tooltip>
  </Box>;
}

/** Botões "Expandir todos" e "Recolher todos". */
export function ExpandAll({onExpand, onCollapse}: {onExpand: () => void; onCollapse: () => void}) {
  return <Stack direction="row" gap={.5}>
    <Button size="small" startIcon={<UnfoldMoreIcon/>} onClick={onExpand}>Expandir todos</Button>
    <Button size="small" startIcon={<UnfoldLessIcon/>} onClick={onCollapse}>Recolher todos</Button>
  </Stack>;
}

/** Confirmação para ações destrutivas, com o texto do botão dizendo exatamente o que acontece. */
export function useConfirm() {
  const [state, setState] = useState<{title: string; text: string; action: string; resolve: (ok: boolean) => void} | null>(null);
  const ask = (title: string, text: string, action: string) => new Promise<boolean>(resolve => setState({title, text, action, resolve}));
  const close = (ok: boolean) => { state?.resolve(ok); setState(null); };
  const dialog = <Dialog open={Boolean(state)} onClose={() => close(false)} maxWidth="xs" fullWidth>
    <DialogTitle>{state?.title}</DialogTitle>
    <DialogContent><Typography color="text.secondary">{state?.text}</Typography></DialogContent>
    <DialogActions><Button onClick={() => close(false)}>Voltar</Button>
      <Button variant="contained" color="error" onClick={() => close(true)}>{state?.action}</Button></DialogActions>
  </Dialog>;
  return {ask, dialog};
}

/** Campo de várias opções (categorias, tags, grupos) com sugestões e criação livre. */
export function MultiPick({label, value, onChange, options, free = true, helper, size = 'medium'}: {label: string; value: string[];
  onChange: (v: string[]) => void; options: {name: string; count?: number}[]; free?: boolean; helper?: string; size?: 'small' | 'medium'}) {
  return <Autocomplete multiple freeSolo={free} size={size} options={options.map(o => o.name)} value={value}
    onChange={(_, v) => onChange((v as string[]).map(x => x.trim()).filter(Boolean))}
    renderOption={(props, option) => { const count = options.find(o => o.name === option)?.count;
      return <li {...props} key={option}><Box flex={1}>{option}</Box>{count != null && <Typography variant="caption">{count}</Typography>}</li>; }}
    renderTags={(v, getTagProps) => v.map((option, index) => <Chip size="small" label={option} {...getTagProps({index})} key={option}/>)}
    renderInput={params => <TextField {...params} label={label} helperText={helper}/>}/>;
}

/** Todos os ids de uma lista paginada com os mesmos filtros, para agir sobre o filtro inteiro e não só a página. */
export async function fetchAllIds(url: string, params: Record<string, unknown>, max = 2000): Promise<number[]> {
  const ids: number[] = [];
  for (let offset = 0; offset < max; offset += 200) {
    const page = await getPage<{id: number}>(url, {...params, limit: 200, offset});
    ids.push(...page.items.map(i => i.id));
    if (!page.items.length || ids.length >= page.total) break;
  }
  return ids;
}

/** Ação em massa em lotes (as rotas aceitam até 200 ids por vez); soma os números que cada lote devolve. */
export async function inBatches(ids: number[], run: (chunk: number[]) => Promise<{data: unknown}>, size = 200): Promise<Record<string, number>> {
  const total: Record<string, number> = {};
  for (let i = 0; i < ids.length; i += size) {
    const {data} = await run(ids.slice(i, i + size));
    if (Array.isArray(data)) total.count = (total.count || 0) + data.length;
    else if (data && typeof data === 'object') for (const [k, v] of Object.entries(data)) if (typeof v === 'number') total[k] = (total[k] || 0) + v;
  }
  return total;
}

/** Uma chamada por item (rotas sem versão em massa). Conta o que deu certo e o que falhou, sem parar no primeiro erro. */
export async function eachItem<T>(items: T[], run: (item: T) => Promise<unknown>): Promise<{ok: number; failed: number}> {
  let ok = 0, failed = 0;
  for (const item of items) { try { await run(item); ok++; } catch { failed++; } }
  return {ok, failed};
}

/** Com a página inteira marcada, oferece marcar todos os itens do filtro (todas as páginas). */
export function SelectMatching({pageCount, pageSelected, selected, total, noun, onSelectAll, onClear}: {pageCount: number; pageSelected: boolean;
  selected: number; total: number; noun: string; onSelectAll: () => Promise<void> | void; onClear: () => void}) {
  const [busy, setBusy] = useState(false);
  if (total <= pageCount || !pageCount) return null;
  if (selected >= total) return <Alert severity="info" sx={{mb: 1.5}} action={<Button color="inherit" size="small" onClick={onClear}>Limpar seleção</Button>}>
    Todos os {total} {noun} do filtro estão selecionados.</Alert>;
  if (!pageSelected) return null;
  return <Alert severity="info" sx={{mb: 1.5}} action={<Button color="inherit" size="small" disabled={busy}
    onClick={async () => { setBusy(true); try { await onSelectAll(); } finally { setBusy(false); } }}>{busy ? 'Selecionando…' : `Selecionar todos os ${total}`}</Button>}>
    Os {pageCount} {noun} desta página estão selecionados.</Alert>;
}
