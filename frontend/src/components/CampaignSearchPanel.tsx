import {useCallback, useEffect, useRef, useState} from 'react';
import {Alert, Box, Button, Card, Checkbox, Chip, CircularProgress, Collapse, FormControlLabel, InputAdornment, LinearProgress, Stack, Switch,
  TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {runSearches} from '../services/sender';
import {GENDER_LABEL} from '../types/campaign';
import type {BestPick, CampaignSearch, Gender, OfficialCategory, SearchFilters, SearchResult} from '../types/campaign';
import type {Niche} from '../types/catalog';
import CategoryTree, {OfficialChip} from './CategoryTree';
import {MultiPick, SelectAll, useConfirm} from './Bulk';
import {PriceTag} from './Ui';
import {DeleteIcon, RefreshIcon} from './Icons';
import {tokens} from '../theme';

const STATUS: Record<CampaignSearch['status'], [string, 'default' | 'info' | 'success' | 'warning' | 'error']> = {
  queued: ['Na fila', 'default'], running: ['Buscando…', 'info'], done: ['Concluída', 'success'], no_results: ['Sem resultados', 'warning'], failed: ['Falhou', 'error'],
};
// Níveis de confiabilidade: cada um preenche os filtros abaixo (vendas, nota, loja oficial/Full e termos suspeitos).
type Trust = SearchFilters['trust'];
const TRUST: Record<Exclude<Trust, 'custom'>, [string, string, Partial<SearchFilters>]> = {
  off: ['Sem filtro', 'Todos os anúncios encontrados.', {min_sold: 0, min_rating: null, official_or_full: false, exclude_suspicious: false}],
  basic: ['Básica', 'Pelo menos 50 vendidos, nota 4 ou mais e sem termos como "banhado", "réplica" ou "1ª linha".',
    {min_sold: 50, min_rating: 4, official_or_full: false, exclude_suspicious: true}],
  high: ['Alta', 'Pelo menos 500 vendidos, nota 4,5 ou mais, só loja oficial ou Full e sem termos suspeitos.',
    {min_sold: 500, min_rating: 4.5, official_or_full: true, exclude_suspicious: true}],
};
const EMPTY_FILTERS: SearchFilters = {min_price: null, max_price: null, min_discount: 0, min_rating: 4, free_shipping: false, allow_uncategorized: false,
  gender: 'any', gender_strict: false, trust: 'basic', min_sold: 50, official_or_full: false, exclude_suspicious: true, source: 'search', offers_pages: 3};
const num = (v: string) => v.trim() === '' ? null : Number(v.replace(',', '.'));
const when = (iso: string) => new Date(iso).toLocaleString('pt-BR', {day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});

type Form = {niche_id: number | null; niche_name: string; categories: OfficialCategory[]; keywords: string[]; exclude_keywords: string[]; filters: SearchFilters};

/** "Buscar produtos para esta campanha": formulário, histórico e resultados com seleção. */
const MAX_TERMS = 10;   // a extensão lê até 10 palavras por busca

const MINUTES_PER_SEARCH = 1.5;   // medido na prática: cada busca de nicho (até 10 palavras) leva cerca de 1,5 min

export default function CampaignSearchPanel({campaignId, defaults, niches = [], chosenNiches = [], onChooseNiches, onAdded}: {campaignId: number;
  defaults: Omit<Form, 'filters'> & {gender?: Gender};
  /** Todos os nichos do perfil; os marcados (chosenNiches) entram em "Buscar nos nichos marcados". */
  niches?: Niche[]; chosenNiches?: number[]; onChooseNiches?: (ids: number[]) => void; onAdded: () => void}) {
  const [form, setForm] = useState<Form>(() => { const {gender, ...rest} = defaults;
    return {...rest, keywords: rest.keywords.slice(0, MAX_TERMS), filters: {...EMPTY_FILTERS, gender: gender ?? 'any'}}; });
  const [history, setHistory] = useState<CampaignSearch[]>([]), [current, setCurrent] = useState<number | null>(null);
  const [results, setResults] = useState<SearchResult[]>([]), [showRejected, setShowRejected] = useState(false), [picked, setPicked] = useState<number[]>([]);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState(false), [advanced, setAdvanced] = useState(false), [tree, setTree] = useState(false);
  // Parecidos: por padrão só o melhor de cada grupo aparece; "+N parecidos" abre o grupo.
  const [oldPicked, setOldPicked] = useState<number[]>([]); const confirm = useConfirm();
  const [grouped, setGrouped] = useState(true), [open, setOpen] = useState<number[]>([]), [bestCount, setBestCount] = useState(10);
  const [perSearch, setPerSearch] = useState(10);
  const chosen = niches.filter(n => chosenNiches.includes(n.id));
  const toggleNiche = (id: number) => onChooseNiches?.(chosenNiches.includes(id) ? chosenNiches.filter(x => x !== id) : [...chosenNiches, id]);
  const set = (patch: Partial<Form>) => setForm(f => ({...f, ...patch}));
  const lastDefaults = useRef('');
  useEffect(() => {   // nichos/categorias mudaram na etapa anterior: atualiza o formulário
    const key = JSON.stringify(defaults);
    if (key !== lastDefaults.current) {
      lastDefaults.current = key;
      const {gender, ...rest} = defaults;
      setForm(f => ({...f, ...rest, keywords: rest.keywords.slice(0, MAX_TERMS), filters: {...f.filters, gender: gender ?? f.filters.gender}}));
    }
  }, [defaults]);

  const loadHistory = useCallback(async () => {
    try { const r = await api.get<CampaignSearch[]>(`/campaigns/${campaignId}/searches`); setHistory(r.data);
      setCurrent(c => c ?? r.data.find(s => ['done', 'no_results'].includes(s.status))?.id ?? null); }
    catch (e) { setError(apiError(e, 'Não foi possível carregar o histórico de buscas.')); }
  }, [campaignId]);
  const loadResults = useCallback(async (id: number) => {
    try { setResults((await api.get<SearchResult[]>(`/campaigns/${campaignId}/searches/${id}/results`, {params: {matched: 'all'}})).data); setPicked([]); setOpen([]); }
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
  const removeSearches = async (ids: number[]) => {
    const finished = history.filter(s => ids.includes(s.id) && ['done', 'no_results'].includes(s.status));
    const waiting = history.filter(s => ids.includes(s.id) && s.status === 'queued').length;
    const detail = [finished.length ? `${finished.length} já terminaram: os resultados delas (${finished.reduce((n, s) => n + s.matched_count, 0)} anúncios nos filtros) são apagados e não dá para desfazer.` : '',
      waiting ? `${waiting} ainda estão na fila e não vão mais rodar.` : '', 'Produtos já adicionados continuam na campanha.'].filter(Boolean).join(' ');
    if (!await confirm.ask(`Excluir ${ids.length} busca(s) do histórico?`, detail, finished.length ? `Excluir e apagar resultados` : 'Excluir')) return;
    try {
      const r = await api.post(`/campaigns/${campaignId}/searches/remove`, {ids});
      setNotice(`${r.data.deleted} busca(s) excluída(s).${r.data.skipped ? ` ${r.data.skipped} em andamento ficaram.` : ''}`);
      setOldPicked([]);
      if (current && ids.includes(current)) { setCurrent(null); setResults([]); }
      loadHistory();
    } catch (e) { setError(apiError(e, 'Não foi possível excluir as buscas.')); }
  };
  /** Preenche a busca com um nicho: categorias, palavras, exclusões e público dele. */
  const fromNiche = (n: Niche) => setForm(f => ({niche_id: n.id, niche_name: n.name, keywords: n.include_keywords.slice(0, MAX_TERMS), exclude_keywords: n.exclude_keywords,
    categories: n.categories.map(c => ({id: c.id, include_children: c.include_children, name: c.name, path: c.path})),
    filters: {...f.filters, gender: n.gender ?? 'any'}}));
  /** Uma busca por nicho da campanha, todas na fila da extensão de uma vez. Os filtros (preço, desconto, confiabilidade) valem para todas. */
  const searchAllNiches = async () => {
    setBusy(true); setError(''); setNotice('');
    try {
      const r = await api.post<{searches: CampaignSearch[]; skipped: string[]}>(`/campaigns/${campaignId}/searches/by-niches`,
        {niche_ids: chosen.map(n => n.id), filters: form.filters});
      setHistory(h => [...r.data.searches, ...h]);
      runSearches().catch(() => {});
      setNotice(`${r.data.searches.length} busca(s) na fila, uma por nicho, cada uma com o público do próprio nicho. Os resultados aparecem no histórico abaixo.`
        + (r.data.skipped.length ? ` Sem palavras nem categorias, ficaram de fora: ${r.data.skipped.join(', ')}.` : ''));
    } catch (e) { setError(apiError(e, 'Não foi possível criar as buscas dos nichos.')); }
    finally { setBusy(false); }
  };
  const tooManyWords = defaults.keywords.length > MAX_TERMS;
  const reuse = (s: CampaignSearch) => setForm({niche_id: s.niche_id, niche_name: s.niche_name, categories: s.categories, keywords: s.keywords,
    exclude_keywords: s.exclude_keywords, filters: {...EMPTY_FILTERS, ...s.filters}});
  const add = async () => {
    try {
      const r = await api.post(`/campaigns/${campaignId}/products`, {listing_ids: picked, search_id: current});
      setNotice(`${r.data.added} produto(s) adicionado(s) à campanha${r.data.skipped ? `, ${r.data.skipped} já estavam nela` : ''}.`);
      onAdded(); loadHistory(); if (current) loadResults(current);
    } catch (e) { setError(apiError(e, 'Não foi possível adicionar os produtos.')); }
  };
  const pickBest = async () => {
    if (!current) return;
    setError(''); setNotice('');
    try {
      const r = await api.post<BestPick>(`/campaigns/${campaignId}/searches/${current}/best`, {count: bestCount});
      setPicked(r.data.listing_ids);
      setNotice(r.data.listing_ids.length
        ? `${r.data.listing_ids.length} melhor(es) marcado(s): um por produto, sem repetir o que já está na campanha e variando categoria e loja. Confira e clique em "Adicionar à campanha".`
        : 'Não há produtos novos para sugerir: os desta busca já estão na campanha ou ficaram fora dos filtros.');
    } catch (e) { setError(apiError(e, 'Não foi possível escolher os melhores.')); }
  };
  /** Adiciona os melhores de cada busca concluída, sem repetir produto entre as buscas. */
  const addBestFromAll = async () => {
    setError(''); setNotice(''); setBusy(true);
    try {
      const r = await api.post<{added: number; searches: {niche_name: string; terms: string[]; added: number}[]}>(`/campaigns/${campaignId}/searches/best-all`, {per_search: perSearch});
      const parts = r.data.searches.filter(s => s.added).map(s => `${s.niche_name || s.terms.slice(0, 2).join(', ')}: ${s.added}`);
      setNotice(r.data.added ? `${r.data.added} produto(s) adicionado(s) à campanha (${parts.join('; ')}). Confira na etapa Seleção dos produtos.`
        : 'Nenhum produto novo: os melhores dessas buscas já estão na campanha.');
      onAdded(); loadHistory(); if (current) loadResults(current);
    } catch (e) { setError(apiError(e, 'Não foi possível adicionar os melhores.')); }
    finally { setBusy(false); }
  };
  const waiting = history.filter(s => s.status === 'queued' || s.status === 'running').length;
  const finishedCount = history.filter(s => s.status === 'done').length;
  const groupOf = (r: SearchResult) => r.group_key ?? r.listing_id;
  const hiddenSimilar = (r: SearchResult) => grouped && r.matched && r.group_best === false && !open.includes(groupOf(r));
  const shown = results.filter(r => (r.matched || showRejected) && !hiddenSimilar(r));
  const selectable = shown.filter(r => r.matched && !r.in_campaign && !r.similar_in_campaign);
  const distinct = new Set(results.filter(r => r.matched).map(groupOf)).size;
  const toggleGroup = (key: number) => setOpen(o => o.includes(key) ? o.filter(x => x !== key) : [...o, key]);
  const active = history.find(s => s.id === current);
  const offers = form.filters.source === 'offers';

  return <Stack gap={2.5}>
    {error && <Alert severity="error" onClose={() => setError('')}>{error}</Alert>}
    {notice && <Alert severity="success" onClose={() => setNotice('')}>{notice}</Alert>}
    <Card variant="outlined" sx={{p: 2}}>
      <Box mb={2.5} pb={2} sx={{borderBottom: `1px solid ${tokens.line}`}}>
        <Typography fontWeight={650} mb={.75}>Onde buscar</Typography>
        <ToggleButtonGroup exclusive size="small" value={offers ? 'offers' : 'search'} aria-label="Onde buscar"
          onChange={(_, v: 'search' | 'offers' | null) => v && set({filters: {...form.filters, source: v}})}
          sx={{'& .MuiToggleButton-root': {textTransform: 'none', px: 2}}}>
          <ToggleButton value="search">Busca por palavras</ToggleButton>
          <ToggleButton value="offers">Ofertas do dia do Mercado Livre</ToggleButton>
        </ToggleButtonGroup>
        <Typography variant="body2" color="text.secondary" mt={.75}>
          {offers ? 'Lê as páginas de Ofertas do dia do ML (várias ofertas boas, já com desconto). As palavras e as categorias do nicho filtram o que aparece; sem palavras nem categorias, vale qualquer oferta que passe nos filtros.'
            : 'Uma busca no Mercado Livre para cada palavra-chave (ou para o nome de cada categoria).'}
        </Typography>
        {offers && <Stack direction="row" alignItems="center" gap={1} mt={1}>
          <Typography fontSize={14}>Páginas lidas:</Typography>
          <ToggleButtonGroup exclusive size="small" value={form.filters.offers_pages ?? 3} aria-label="Páginas de ofertas"
            onChange={(_, v: number | null) => v && set({filters: {...form.filters, offers_pages: v}})}>
            {[1, 2, 3, 4, 5].map(n => <ToggleButton key={n} value={n} sx={{px: 1.5}}>{n}</ToggleButton>)}
          </ToggleButtonGroup>
          <Typography variant="caption" color="text.secondary">cerca de 50 ofertas por página</Typography>
        </Stack>}
      </Box>
      {niches.length > 0 && <Box mb={2.5} pb={2} sx={{borderBottom: `1px solid ${tokens.line}`}}>
        <Stack direction={{xs: 'column', sm: 'row'}} gap={1} justifyContent="space-between" alignItems={{sm: 'center'}} mb={1}>
          <Box>
            <Typography fontWeight={650}>Buscar pelos nichos</Typography>
            <Typography variant="body2" color="text.secondary">Marque os nichos. Cada um vira uma busca com as palavras, categorias e o público dele.
              A confiabilidade e os filtros de preço abaixo valem para todas.</Typography>
          </Box>
          <Button variant="contained" disabled={busy || !chosen.length} onClick={searchAllNiches} sx={{flexShrink: 0}}>
            {chosen.length ? `Buscar nos ${chosen.length} nicho(s) marcado(s)` : 'Marque os nichos'}</Button>
        </Stack>
        <Stack direction="row" gap={.75} flexWrap="wrap" mb={1}>
          {niches.map(n => { const on = chosenNiches.includes(n.id);
            return <Chip key={n.id} clickable color={on ? 'primary' : 'default'} variant={on ? 'filled' : 'outlined'}
              label={`${on ? '✓ ' : ''}${n.favorite ? '★ ' : ''}${n.name}`} onClick={() => toggleNiche(n.id)}/>; })}
          {niches.length > 1 && <Button size="small" onClick={() => onChooseNiches?.(chosen.length === niches.length ? [] : niches.map(n => n.id))}>
            {chosen.length === niches.length ? 'Desmarcar todos' : 'Marcar todos'}</Button>}
        </Stack>
        {chosen.length > 0 && <Typography variant="caption" display="block" mb={1}>
          Leva cerca de {Math.ceil(chosen.length * MINUTES_PER_SEARCH)} min ({MINUTES_PER_SEARCH.toString().replace('.', ',')} min por nicho). Pode continuar nas outras etapas enquanto isso.</Typography>}
        <Typography variant="caption" display="block" mb={.5}>Ou preencha a busca manual abaixo com um nicho:</Typography>
        <Stack direction="row" gap={.75} flexWrap="wrap">{niches.map(n => <Chip key={n.id} size="small" clickable
          color={form.niche_id === n.id ? 'primary' : 'default'} variant={form.niche_id === n.id ? 'filled' : 'outlined'}
          label={`${n.favorite ? '★ ' : ''}${n.name}`} onClick={() => fromNiche(n)}/>)}</Stack>
        {tooManyWords && <Alert severity="info" sx={{mt: 1.5}}>Os nichos juntos têm {defaults.keywords.length} palavras e cada busca aceita até {MAX_TERMS}.
          Use "Buscar em todos os nichos" ou escolha um nicho acima.</Alert>}
      </Box>}
      <Typography fontWeight={650} mb={1.5}>Nova busca{form.niche_name ? ` (nicho ${form.niche_name})` : ''}</Typography>
      <Stack gap={2}>
        <MultiPick label={offers ? 'Palavras que o título precisa ter (basta uma)' : 'Palavras-chave (uma busca no Mercado Livre para cada)'}
          value={form.keywords} onChange={v => set({keywords: v.slice(0, 10)})} options={[]}
          helper={offers ? 'Opcional. Vazio = todas as ofertas do dia que passarem nas categorias e nos filtros.' : 'Até 10. Sem palavras, o nome de cada categoria vira a palavra de busca.'}/>
        <Box>
          <Typography fontSize={14} fontWeight={600} mb={.75}>Confiabilidade</Typography>
          <ToggleButtonGroup exclusive size="small" value={form.filters.trust === 'custom' ? null : form.filters.trust} aria-label="Confiabilidade"
            onChange={(_, v: Exclude<Trust, 'custom'> | null) => v && set({filters: {...form.filters, ...TRUST[v][2], trust: v}})}
            sx={{'& .MuiToggleButton-root': {textTransform: 'none', px: 2}}}>
            {(Object.keys(TRUST) as Exclude<Trust, 'custom'>[]).map(k => <ToggleButton key={k} value={k}>{TRUST[k][0]}</ToggleButton>)}
          </ToggleButtonGroup>
          <Typography variant="body2" color="text.secondary" mt={.75}>
            {form.filters.trust === 'custom' ? 'Personalizada: ajustada nos filtros abaixo.' : TRUST[form.filters.trust][1]}
          </Typography>
        </Box>
        <Box>
          <Typography fontSize={14} fontWeight={600} mb={.75}>Público</Typography>
          <ToggleButtonGroup exclusive size="small" value={form.filters.gender} aria-label="Público"
            onChange={(_, v: Gender | null) => v && set({filters: {...form.filters, gender: v}})} sx={{'& .MuiToggleButton-root': {textTransform: 'none', px: 2}}}>
            {(Object.keys(GENDER_LABEL) as Gender[]).map(g => <ToggleButton key={g} value={g}>{GENDER_LABEL[g]}</ToggleButton>)}
          </ToggleButtonGroup>
          {form.filters.gender !== 'any' && <Box mt={.75}>
            <Typography variant="body2" color="text.secondary">
              Cada palavra é buscada com "{form.filters.gender === 'male' ? 'masculino' : 'feminino'}" e anúncios do outro público ficam de fora. Unissex continua valendo.
            </Typography>
            <FormControlLabel control={<Switch size="small" checked={form.filters.gender_strict}
              onChange={e => set({filters: {...form.filters, gender_strict: e.target.checked}})}/>}
              label={`Só anúncios que dizem "${form.filters.gender === 'male' ? 'masculino' : 'feminino'}" ou "unissex" no título`}/>
          </Box>}
        </Box>
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
          <Button size="small" onClick={() => setAdvanced(a => !a)} aria-expanded={advanced}>{advanced ? 'Ocultar filtros' : 'Filtros de preço, desconto, nota e vendas'}</Button>
          <Collapse in={advanced}><Stack direction={{xs: 'column', sm: 'row'}} gap={1.5} mt={1.5} flexWrap="wrap" useFlexGap>
            <TextField size="small" label="Preço mínimo" value={form.filters.min_price ?? ''} onChange={e => set({filters: {...form.filters, min_price: num(e.target.value)}})}
              InputProps={{startAdornment: <InputAdornment position="start">R$</InputAdornment>}} sx={{width: 150}}/>
            <TextField size="small" label="Preço máximo" value={form.filters.max_price ?? ''} onChange={e => set({filters: {...form.filters, max_price: num(e.target.value)}})}
              InputProps={{startAdornment: <InputAdornment position="start">R$</InputAdornment>}} sx={{width: 150}}/>
            <TextField size="small" type="number" label="Desconto mínimo (%)" value={form.filters.min_discount} sx={{width: 170}}
              onChange={e => set({filters: {...form.filters, min_discount: Math.max(0, Math.min(95, Number(e.target.value) || 0))}})}/>
            <TextField size="small" label="Nota mínima" value={form.filters.min_rating ?? ''} sx={{width: 120}} onChange={e => set({filters: {...form.filters, min_rating: num(e.target.value), trust: 'custom'}})}/>
            <TextField size="small" type="number" label="Vendidos mínimos" value={form.filters.min_sold} sx={{width: 150}}
              onChange={e => set({filters: {...form.filters, min_sold: Math.max(0, Number(e.target.value) || 0), trust: 'custom'}})}/>
            <FormControlLabel control={<Switch checked={form.filters.official_or_full} onChange={e => set({filters: {...form.filters, official_or_full: e.target.checked, trust: 'custom'}})}/>}
              label="Só loja oficial ou Full"/>
            <FormControlLabel control={<Switch checked={form.filters.exclude_suspicious} onChange={e => set({filters: {...form.filters, exclude_suspicious: e.target.checked, trust: 'custom'}})}/>}
              label='Excluir "banhado", "réplica", "1ª linha" e afins'/>
            <FormControlLabel control={<Switch checked={form.filters.free_shipping} onChange={e => set({filters: {...form.filters, free_shipping: e.target.checked}})}/>} label="Só frete grátis"/>
            <FormControlLabel control={<Switch checked={form.filters.allow_uncategorized} onChange={e => set({filters: {...form.filters, allow_uncategorized: e.target.checked}})}/>}
              label="Aceitar anúncios sem categoria identificada"/>
          </Stack></Collapse>
        </Box>
        <Box><Button variant="contained" disabled={busy || (!offers && !form.keywords.length && !form.categories.length)} onClick={() => start({
          niche_id: form.niche_id, categories: form.categories.map(c => ({id: c.id, include_children: c.include_children})), keywords: form.keywords,
          exclude_keywords: form.exclude_keywords, filters: form.filters})}>{busy ? 'Enviando…' : 'Buscar produtos'}</Button></Box>
      </Stack>
    </Card>

    <Box>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
        <Box>
          <Typography fontWeight={650}>Buscas desta campanha ({history.length})</Typography>
          {waiting > 0 && <Typography variant="caption" color="info.main">Faltam {waiting} busca(s), cerca de {Math.ceil(waiting * MINUTES_PER_SEARCH)} min. A lista se atualiza sozinha.</Typography>}
        </Box>
        <Stack direction="row" gap={.5} alignItems="center">
          {history.length > 0 && <SelectAll total={history.length} selected={oldPicked.length} onAll={() => setOldPicked(history.map(s => s.id))} onNone={() => setOldPicked([])} label="Todas"/>}
          {oldPicked.length > 0 && <Button size="small" color="error" startIcon={<DeleteIcon/>} onClick={() => removeSearches(oldPicked)}>Excluir {oldPicked.length}</Button>}
          <Tooltip title="Atualizar"><Button size="small" startIcon={<RefreshIcon/>} onClick={loadHistory}>Atualizar</Button></Tooltip>
        </Stack>
      </Stack>
      {!history.length ? <Typography variant="body2" color="text.secondary">Nenhuma busca ainda. A primeira aparece aqui com o andamento.</Typography>
        : <Card variant="outlined" sx={{maxHeight: 260, overflow: 'auto'}}>{history.map(s => { const [label, color] = STATUS[s.status];
          return <Stack key={s.id} direction={{xs: 'column', sm: 'row'}} gap={1} alignItems={{sm: 'center'}} sx={{px: 1.5, py: 1, borderBottom: `1px solid ${tokens.line}`,
            bgcolor: s.id === current ? tokens.paper : 'transparent'}}>
            <Checkbox size="small" checked={oldPicked.includes(s.id)} sx={{p: .5, alignSelf: {xs: 'flex-start', sm: 'center'}}}
              onChange={() => setOldPicked(p => p.includes(s.id) ? p.filter(x => x !== s.id) : [...p, s.id])} inputProps={{'aria-label': 'Selecionar busca'}}/>
            <Box flex={1} minWidth={0}>
              <Typography fontSize={14} fontWeight={600} noWrap>{s.niche_name ? `${s.niche_name}: ` : ''}{s.terms.join(', ')}</Typography>
              <Typography variant="caption">{when(s.created_at)}{s.niche_name ? `, nicho ${s.niche_name}` : ''}{s.categories.length ? `, ${s.categories.length} categoria(s)` : ''}{s.filters?.gender && s.filters.gender !== 'any' ? `, público ${GENDER_LABEL[s.filters.gender].toLowerCase()}` : ''}
                {['done', 'no_results'].includes(s.status) ? `, ${s.result_count} encontrados, ${s.matched_count} nos filtros, ${s.added_count} adicionados` : ''}</Typography>
              {s.error && <Typography variant="caption" color="error.main" display="block">{s.error}</Typography>}
            </Box>
            <Chip size="small" color={color} label={label} icon={s.status === 'running' || s.status === 'queued' ? <CircularProgress size={12}/> : undefined}/>
            <Stack direction="row" gap={.5}>
              {['done', 'no_results'].includes(s.status) && <Button size="small" onClick={() => setCurrent(s.id)}>Ver resultados</Button>}
              <Button size="small" onClick={() => repeat(s)}>Repetir</Button>
              <Button size="small" onClick={() => reuse(s)}>Usar parâmetros</Button>
              {s.status !== 'running' && <Button size="small" color="error" onClick={() => removeSearches([s.id])}>Excluir</Button>}
            </Stack>
          </Stack>; })}</Card>}
      {pending && <LinearProgress sx={{mt: 1}} variant={history.length ? 'determinate' : 'indeterminate'}
        value={history.length ? (history.length - waiting) * 100 / history.length : undefined}/>}
      {finishedCount > 0 && <Card variant="outlined" sx={{p: 1.5, mt: 1.5, bgcolor: tokens.paper}}>
        <Stack direction={{xs: 'column', sm: 'row'}} gap={1.5} alignItems={{sm: 'center'}}>
          <Box flex={1}>
            <Typography fontWeight={600} fontSize={14.5}>Montar a campanha com os melhores</Typography>
            <Typography variant="body2" color="text.secondary">Pega os melhores de cada uma das {finishedCount} busca(s) concluída(s): um por produto, sem repetir o que
              já está na campanha e variando categoria e loja.{waiting ? ' As que ainda estão rodando entram se você clicar de novo depois.' : ''}</Typography>
          </Box>
          <TextField size="small" type="number" label="Por busca" value={perSearch} sx={{width: 100}}
            onChange={e => setPerSearch(Math.max(1, Math.min(100, Number(e.target.value) || 1)))}/>
          <Button variant="contained" disabled={busy} onClick={addBestFromAll}>Adicionar até {perSearch * finishedCount}</Button>
        </Stack>
      </Card>}
    </Box>

    {active && <Box>
      <Stack direction={{xs: 'column', sm: 'row'}} justifyContent="space-between" alignItems={{sm: 'center'}} gap={1} mb={1}>
        <Box>
          <Typography fontWeight={650}>Resultados: {active.terms.join(', ')}</Typography>
          {results.some(r => r.matched) && <Typography variant="caption">
            {results.filter(r => r.matched).length} anúncio(s) nos filtros, {distinct} produto(s) diferente(s)</Typography>}
        </Box>
        <Stack direction="row" gap={1} flexWrap="wrap">
          <FormControlLabel control={<Switch size="small" checked={grouped} onChange={e => setGrouped(e.target.checked)}/>} label="Agrupar parecidos"/>
          <FormControlLabel control={<Switch size="small" checked={showRejected} onChange={e => setShowRejected(e.target.checked)}/>}
            label={`Mostrar fora dos filtros (${results.filter(r => !r.matched).length})`}/>
        </Stack>
      </Stack>
      {!shown.length ? <Alert severity="info">{active.status === 'no_results' || !results.length
        ? 'Nenhum anúncio passou nos filtros desta busca. Tente outras palavras-chave, inclua subcategorias ou aceite anúncios sem categoria identificada.'
        : 'Todos os resultados ficaram fora dos filtros. Ligue "Mostrar fora dos filtros" para ver os motivos.'}</Alert> : <>
        <Stack direction="row" alignItems="center" gap={1} flexWrap="wrap" mb={1}>
          <TextField size="small" type="number" label="Quantos" value={bestCount} sx={{width: 96}}
            onChange={e => setBestCount(Math.max(1, Math.min(200, Number(e.target.value) || 1)))}/>
          <Tooltip title="Marca os melhores: um por produto (o melhor entre os parecidos), sem repetir o que já está na campanha e variando categoria e loja.">
            <Button variant="outlined" onClick={pickBest}>Escolher os melhores</Button>
          </Tooltip>
          <SelectAll total={selectable.length} selected={picked.length} onAll={() => setPicked(selectable.map(r => r.listing_id))} onNone={() => setPicked([])}/>
          <Button variant="contained" disabled={!picked.length} onClick={add}>Adicionar {picked.length || ''} à campanha</Button>
        </Stack>
        <Card variant="outlined" sx={{maxHeight: 520, overflow: 'auto'}}>{shown.map(r =>
          <Stack key={r.listing_id} direction="row" gap={1.5} alignItems="flex-start" sx={{p: 1.25, borderBottom: `1px solid ${tokens.line}`, opacity: r.matched ? 1 : .6,
            ...(grouped && r.matched && r.group_best === false ? {pl: 5, bgcolor: tokens.paper} : {})}}>
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
                {r.official_store && <Chip size="small" color="primary" variant="outlined" label="Loja oficial"/>}
                {r.fulfillment && <Chip size="small" color="success" variant="outlined" label="Full"/>}
                {r.in_campaign && <Chip size="small" color="success" label="Já na campanha"/>}
                {r.similar_in_campaign && <Chip size="small" color="warning" variant="outlined" label="Parecido com um já na campanha"/>}
                {r.matched && r.cheapest && <Chip size="small" color="success" variant="outlined" label="Menor preço entre os parecidos"/>}
                {grouped && r.matched && r.group_best && (r.group_size ?? 1) > 1 && <Chip size="small" clickable color="info" variant={open.includes(groupOf(r)) ? 'filled' : 'outlined'}
                  label={open.includes(groupOf(r)) ? 'Ocultar parecidos' : `+${(r.group_size ?? 1) - 1} parecido(s)`} onClick={() => toggleGroup(groupOf(r))}/>}
                {grouped && r.matched && r.group_best === false && <Chip size="small" variant="outlined" label="Parecido"/>}
                {!r.matched && <Chip size="small" color="warning" label={r.reason}/>}
                <Typography variant="caption">Nota {r.score}{r.rating ? `, ★ ${r.rating}` : ''}{r.sold != null ? `, ${r.sold.toLocaleString('pt-BR')} vendidos` : ''}, busca "{r.term}"</Typography>
              </Stack>
            </Box>
          </Stack>)}</Card>
      </>}
    </Box>}
    {confirm.dialog}
  </Stack>;
}
