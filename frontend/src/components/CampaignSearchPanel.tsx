import {useCallback, useEffect, useRef, useState} from 'react';
import {Alert, Box, Button, Card, Checkbox, Chip, CircularProgress, Collapse, FormControlLabel, InputAdornment, LinearProgress, Stack, Switch,
  TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {runSearches} from '../services/sender';
import type {CampaignSearch, OfficialCategory, SearchFilters, SearchResult} from '../types/campaign';
import CategoryTree, {OfficialChip} from './CategoryTree';
import {MultiPick, SelectAll} from './Bulk';
import {PriceTag} from './Ui';
import {RefreshIcon} from './Icons';
import {tokens} from '../theme';

const STATUS: Record<CampaignSearch['status'], [string, 'default' | 'info' | 'success' | 'warning' | 'error']> = {
  queued: ['Na fila', 'default'], running: ['Buscando…', 'info'], done: ['Concluída', 'success'], no_results: ['Sem resultados', 'warning'], failed: ['Falhou', 'error'],
};
const EMPTY_FILTERS: SearchFilters = {min_price: null, max_price: null, min_discount: 0, min_rating: null, free_shipping: false, allow_uncategorized: false};
const num = (v: string) => v.trim() === '' ? null : Number(v.replace(',', '.'));
const when = (iso: string) => new Date(iso).toLocaleString('pt-BR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});

type Form = {niche_id: number | null; niche_name: string; categories: OfficialCategory[]; keywords: string[]; exclude_keywords: string[]; filters: SearchFilters};

/** "Buscar produtos para esta campanha": formulário, histórico e resultados com seleção. */
export default function CampaignSearchPanel({campaignId, defaults, onAdded}: {campaignId: number; defaults: Omit<Form, 'filters'>; onAdded: () => void}) {
  const [form, setForm] = useState<Form>({...defaults, filters: EMPTY_FILTERS});
  const [history, setHistory] = useState<CampaignSearch[]>([]), [current, setCurrent] = useState<number | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]), [showRejected, setShowRejected] = useState(false), [picked, setPicked] = useState<number[]>([]);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [advanced, setAdvanced] = useState(false), [tree, setTree] = useState(false);
  const set = (patch: Partial<Form>) => setForm(f => ({...f, ...patch}));
  const lastDefaults = useRef('');
  useEffect(() => {   // nichos/categorias mudaram na etapa anterior: atualiza o formulário
    const key = JSON.stringify(defaults);
    if (key !== lastDefaults.current) { lastDefaults.current = key; setForm(f => ({...f, ...defaults})); }
  }, [defaults]);

  const loadHistory = useCallback(async () => {
    try { const r = await api.get<CampaignSearch[]>(`/campaigns/${campaignId}/searches`); setHistory(r.data);
      setCurrent(c => c ?? r.data.find(s => ['done', 'no_results'].includes(s.status))?.id ?? null); }
    catch (e) { setError(apiError(e, 'Não foi possível carregar o histórico de buscas.')); }
  }, [campaignId]);
  const loadResults = useCallback(async (id: number) => {
    try { setResults((await api.get<SearchResult[]>(`/campaigns/${campaignId}/searches/${id}/results`, {params: {matched: 'all'}})).data); setPicked([]); }
    catch (e) { setError(apiError(e, 'Não foi possível carregar os resultados.')); }
  }, [campaignId]);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => { if (current) loadResults(current); }, [current, loadResults]);
  // Enquanto houver busca na fila ou rodando, atualiza a cada 3 s.
  const pending = history.some(s => s.status === 'queued' || s.status === 'running');
  useEffect(() => {
    if (!pending) return;
    const t = setInterval(async () => {
      const before = history.filter(s => s.status === 'queued' || s.status === 'running').map(s => s.id);
      const r = await api.get<CampaignSearch[]>(`/campaigns/${campaignId}/searches`).catch(() => null);
      if (!r) return;
      setHistory(r.data);
      const finished = r.data.find(s => before.includes(s.id) && !['queued', 'running'].includes(s.status));
      if (finished) { setCurrent(finished.id); loadResults(finished.id); }
    }, 3000);
    return () => clearInterval(t);
  }, [pending, history, campaignId, loadResults]);

  const start = async (body: object) => {
    setBusy(true); setError(''); setNotice('');
    try {
      const r = await api.post<CampaignSearch>(`/campaigns/${campaignId}/searches`, body);
      setHistory(h => [r.data, ...h]);
      runSearches().catch(() => {});   // pede à extensão para começar já (sem esperar os 30 s do ciclo)
      setNotice(`Busca enviada para a extensão: ${r.data.terms.join(', ')}. Os resultados aparecem aqui em instantes.`);
    } catch (e) { setError(apiError(e, 'Não foi possível iniciar a busca.')); }
    finally { setBusy(false); }
  };
  const repeat = async (s: CampaignSearch) => {
    try { const r = await api.post<CampaignSearch>(`/campaigns/${campaignId}/searches/${s.id}/repeat`); setHistory(h => [r.data, ...h]); runSearches().catch(() => {}); }
    catch (e) { setError(apiError(e, 'Não foi possível repetir a busca.')); }
  };
  const reuse = (s: CampaignSearch) => setForm({niche_id: s.niche_id, niche_name: s.niche_name, categories: s.categories, keywords: s.keywords,
    exclude_keywords: s.exclude_keywords, filters: {...EMPTY_FILTERS, ...s.filters}});
  const add = async () => {
    try {
      const r = await api.post(`/campaigns/${campaignId}/products`, {listing_ids: picked, search_id: current});
      setNotice(`${r.data.added} produto(s) adicionado(s) à campanha${r.data.skipped ? `, ${r.data.skipped} já estavam nela` : ''}.`);
      onAdded(); loadHistory(); if (current) loadResults(current);
    } catch (e) { setError(apiError(e, 'Não foi possível adicionar os produtos.')); }
  };
  const shown = results.filter(r => r.matched || showRejected);
  const selectable = shown.filter(r => r.matched && !r.in_campaign);
  const active = history.find(s => s.id === current);

  return <Stack gap={2.5}>
    {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
    {notice && <Alert severity="success" onClose={() => setNotice('')}>{notice}</Alert>}
    <Card variant="outlined" sx={{p: 2}}>
      <Typography fontWeight={650} mb={1.5}>Nova busca{form.niche_name ? ` (nicho ${form.niche_name})` : ''}</Typography>
      <Stack gap={2}>
        <MultiPick label="Palavras-chave (uma busca no Mercado Livre para cada)" value={form.keywords} onChange={v => set({keywords: v.slice(0, 10)})} options={[]}
          helper="Até 10. Sem palavras, o nome de cada categoria vira a palavra de busca."/>
        <Box>
          <Stack direction="row" alignItems="center" justifyContent="space-between" mb={.75}>
            <Typography fontSize={14} fontWeight={600}>Categorias oficiais aceitas</Typography>
            <Button size="small" onClick={() => setTree(t => !t)} aria-expanded={tree}>{tree ? 'Fechar árvore' : 'Escolher na árvore'}</Button>
          </Stack>
          {!tree && <Stack direction="row" gap={.5} flexWrap="wrap">{form.categories.length ? form.categories.map(c => <OfficialChip key={c.id} cat={c}
            onDelete={() => set({categories: form.categories.filter(x => x.id !== c.id)})}
            onToggleChildren={() => set({categories: form.categories.map(x => x.id === c.id ? {...x, include_children: !x.include_children} : x)})}/>)
            : <Typography variant="body2" color="text.secondary">Qualquer categoria. Escolha categorias para manter só os anúncios delas.</Typography>}</Stack>}
          <Collapse in={tree} unmountOnExit><CategoryTree selected={form.categories} onChange={v => set({categories: v})} height={300}/></Collapse>
        </Box>
        <MultiPick label="Palavras excluídas do título" value={form.exclude_keywords} onChange={v => set({exclude_keywords: v})} options={[]}/>
        <Box>
          <Button size="small" onClick={() => setAdvanced(a => !a)} aria-expanded={advanced}>{advanced ? 'Ocultar filtros' : 'Filtros de preço, desconto e nota'}</Button>
          <Collapse in={advanced}><Stack direction={{xs: 'column', sm: 'row'}} gap={1.5} mt={1.5} flexWrap="wrap" useFlexGap>
            <TextField size="small" label="Preço mínimo" value={form.filters.min_price ?? ''} onChange={e => set({filters: {...form.filters, min_price: num(e.target.value)}})}
              InputProps={{startAdornment: <InputAdornment position="start">R$</InputAdornment>}} sx={{width: 150}}/>
            <TextField size="small" label="Preço máximo" value={form.filters.max_price ?? ''} onChange={e => set({filters: {...form.filters, max_price: num(e.target.value)}})}
              InputProps={{startAdornment: <InputAdornment position="start">R$</InputAdornment>}} sx={{width: 150}}/>
            <TextField size="small" type="number" label="Desconto mínimo (%)" value={form.filters.min_discount} sx={{width: 170}}
              onChange={e => set({filters: {...form.filters, min_discount: Math.max(0, Math.min(95, Number(e.target.value) || 0))}})}/>
            <TextField size="small" label="Nota mínima" value={form.filters.min_rating ?? ''} sx={{width: 120}} onChange={e => set({filters: {...form.filters, min_rating: num(e.target.value)}})}/>
            <FormControlLabel control={<Switch checked={form.filters.free_shipping} onChange={e => set({filters: {...form.filters, free_shipping: e.target.checked}})}/>} label="Só frete grátis"/>
            <FormControlLabel control={<Switch checked={form.filters.allow_uncategorized} onChange={e => set({filters: {...form.filters, allow_uncategorized: e.target.checked}})}/>}
              label="Aceitar anúncios sem categoria identificada"/>
          </Stack></Collapse>
        </Box>
        <Box><Button variant="contained" disabled={busy || (!form.keywords.length && !form.categories.length)} onClick={() => start({
          niche_id: form.niche_id, categories: form.categories.map(c => ({id: c.id, include_children: c.include_children})), keywords: form.keywords,
          exclude_keywords: form.exclude_keywords, filters: form.filters})}>{busy ? 'Enviando…' : 'Buscar produtos'}</Button></Box>
      </Stack>
    </Card>

    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography fontWeight={650}>Buscas desta campanha ({history.length})</Typography>
        <Tooltip title="Atualizar"><Button size="small" startIcon={<RefreshIcon/>} onClick={loadHistory}>Atualizar</Button></Tooltip>
      </Stack>
      {!history.length ? <Typography variant="body2" color="text.secondary">Nenhuma busca ainda. A primeira aparece aqui com o andamento.</Typography>
        : <Card variant="outlined" sx={{maxHeight: 260, overflow: 'auto'}}>{history.map(s => { const [label, color] = STATUS[s.status];
          return <Stack key={s.id} direction={{xs: 'column', sm: 'row'}} gap={1} alignItems={{sm: 'center'}} sx={{px: 1.5, py: 1, borderBottom: `1px solid ${tokens.line}`,
            bgcolor: s.id === current ? tokens.paper : 'transparent'}}>
            <Box flex={1} minWidth={0}>
              <Typography fontSize={14} fontWeight={600} noWrap>{s.terms.join(', ')}</Typography>
              <Typography variant="caption">{when(s.created_at)}{s.niche_name ? `, nicho ${s.niche_name}` : ''}{s.categories.length ? `, ${s.categories.length} categoria(s)` : ''}
                {['done', 'no_results'].includes(s.status) ? `, ${s.result_count} encontrados, ${s.matched_count} nos filtros, ${s.added_count} adicionados` : ''}</Typography>
              {s.error && <Typography variant="caption" color="error.main" display="block">{s.error}</Typography>}
            </Box>
            <Chip size="small" color={color} label={label} icon={s.status === 'running' || s.status === 'queued' ? <CircularProgress size={12}/> : undefined}/>
            <Stack direction="row" gap={.5}>
              {['done', 'no_results'].includes(s.status) && <Button size="small" onClick={() => setCurrent(s.id)}>Ver resultados</Button>}
              <Button size="small" onClick={() => repeat(s)}>Repetir</Button>
              <Button size="small" onClick={() => reuse(s)}>Usar parâmetros</Button>
            </Stack>
          </Stack>; })}</Card>}
      {pending && <LinearProgress sx={{mt: 1}}/>}
    </Box>

    {active && <Box>
      <Stack direction={{xs: 'column', sm: 'row'}} justifyContent="space-between" alignItems={{sm: 'center'}} gap={1} mb={1}>
        <Typography fontWeight={650}>Resultados: {active.terms.join(', ')}</Typography>
        <FormControlLabel control={<Switch size="small" checked={showRejected} onChange={e => setShowRejected(e.target.checked)}/>}
          label={`Mostrar fora dos filtros (${results.filter(r => !r.matched).length})`}/>
      </Stack>
      {!shown.length ? <Alert severity="info">{active.status === 'no_results' || !results.length
        ? 'Nenhum anúncio passou nos filtros desta busca. Tente outras palavras-chave, inclua subcategorias ou aceite anúncios sem categoria identificada.'
        : 'Todos os resultados ficaram fora dos filtros. Ligue "Mostrar fora dos filtros" para ver os motivos.'}</Alert> : <>
        <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" mb={1}>
          <SelectAll total={selectable.length} selected={picked.length} onAll={() => setPicked(selectable.map(r => r.listing_id))} onNone={() => setPicked([])}/>
          <Button variant="contained" disabled={!picked.length} onClick={add}>Adicionar {picked.length || ''} à campanha</Button>
        </Stack>
        <Card variant="outlined" sx={{maxHeight: 520, overflow: 'auto'}}>{shown.map(r =>
          <Stack key={r.listing_id} direction="row" gap={1.5} alignItems="flex-start" sx={{p: 1.25, borderBottom: `1px solid ${tokens.line}`, opacity: r.matched ? 1 : .6}}>
            <Checkbox checked={picked.includes(r.listing_id) || r.in_campaign} disabled={!r.matched || r.in_campaign} sx={{p: .5}}
              onChange={() => setPicked(p => p.includes(r.listing_id) ? p.filter(x => x !== r.listing_id) : [...p, r.listing_id])} inputProps={{'aria-label': `Selecionar ${r.title}`}}/>
            <Box component="img" src={r.image_url} alt="" referrerPolicy="no-referrer" sx={{width: 64, height: 64, objectFit: 'contain', borderRadius: 1.5, bgcolor: '#fff', flexShrink: 0, border: `1px solid ${tokens.line}`}}/>
            <Box flex={1} minWidth={0}>
              <Typography fontSize={14.5} fontWeight={600} sx={{display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>
                <a href={r.url} target="_blank" rel="noreferrer" style={{color: 'inherit'}}>{r.title}</a></Typography>
              <Box my={.5}><PriceTag price={r.price} original={r.original_price} note={r.price_note} size="sm"/></Box>
              <Stack direction="row" gap={.5} flexWrap="wrap" alignItems="center">
                {r.ml_category_id ? <OfficialChip cat={{id: r.ml_category_id, include_children: false, name: r.category_name || r.ml_category_id, path: r.category_path, is_leaf: true}}/>
                  : <Chip size="small" variant="outlined" label="Categoria não identificada"/>}
                {r.in_campaign && <Chip size="small" color="success" label="Já na campanha"/>}
                {!r.matched && <Chip size="small" color="warning" label={r.reason}/>}
                <Typography variant="caption">Nota {r.score}{r.rating ? `, ★ ${r.rating}` : ''}, busca "{r.term}"</Typography>
              </Stack>
            </Box>
          </Stack>)}</Card>
      </>}
    </Box>}
  </Stack>;
}
