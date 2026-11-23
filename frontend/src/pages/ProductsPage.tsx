import {ChangeEvent, useEffect, useRef, useState} from 'react';
import {useNavigate, useSearchParams} from 'react-router-dom';
import {Alert, Autocomplete, Badge, Box, Button, Card, CardContent, Checkbox, Chip, CircularProgress, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, Grid, IconButton, InputAdornment, LinearProgress, Menu, MenuItem, Stack, TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {captureInBrowser, extensionStatus} from '../services/sender';
import type {Product} from '../types/product';
import {needsBrowser, productLabel, productStatuses, timeAgo} from '../labels';
import {usePaged} from '../hooks/usePaged';
import {Empty, Feedback, Loading, LoadMore} from '../components/Feedback';
import {Meta, PageHeader, PriceTag} from '../components/Ui';
import WhatsAppPreview from '../components/WhatsAppPreview';
import {BulkBar, MultiPick, SelectAll, SelectMatching, fetchAllIds, inBatches, useConfirm, useSelection} from '../components/Bulk';
import {AddIcon, DeleteIcon, FilterIcon, RefreshIcon, SearchIcon, TagIcon} from '../components/Icons';
import type {CampaignOptions} from '../types/campaign';

type Draft = {tags: string[]; title: string; description: string; price: string; original_price: string; price_note: string; affiliate_url: string; category: string; marketplace: string; store: string; notes: string};
const toDraft = (p: Product): Draft => ({tags: p.tags || [], title: p.title, description: p.description, price: p.price?.toString() ?? '', original_price: p.original_price?.toString() ?? '',
  price_note: p.price_note || '', affiliate_url: p.affiliate_url, category: p.category, marketplace: p.marketplace, store: p.store, notes: p.notes});
const toNumber = (value: string) => { let t = value.trim().replace(/R\$\s?/, ''); if (!t) return null; if (t.includes(',')) t = t.replace(/\./g, '').replace(',', '.'); const n = Number(t); return Number.isFinite(n) && n >= 0 ? n : null; };
const STALE_HOURS = 6;
const isStale = (p: Product) => !p.captured_at || Date.now() - new Date(p.captured_at).getTime() > STALE_HOURS * 3600e3;
const browserReadable = (p: Product) => needsBrowser(p.original_url) || p.data_source === 'browser';

export default function ProductsPage() {
  const [params, setParams] = useSearchParams();
  const status = params.get('status') || '';
  const filters = {category: params.get('category') || '', tag: params.get('tag') || '', sort: params.get('sort') || 'newest',
    created_from: params.get('from') || ''};
  const [query, setQuery] = useState(''), [search, setSearch] = useState('');
  const listParams = {status: status || undefined, q: search || undefined, category: filters.category || undefined,
    tag: filters.tag || undefined, sort: filters.sort, created_from: filters.created_from ? new Date(filters.created_from).toISOString() : undefined};
  const list = usePaged<Product>('/products', listParams);
  const navigate = useNavigate();
  const sel = useSelection(); const confirm = useConfirm();
  const [facets, setFacets] = useState<CampaignOptions | null>(null), [showFilters, setShowFilters] = useState(false);
  const [bulkDialog, setBulkDialog] = useState<'category' | 'tags' | null>(null), [bulkCategory, setBulkCategory] = useState('');
  const [bulkAdd, setBulkAdd] = useState<string[]>([]), [bulkRemove, setBulkRemove] = useState<string[]>([]);
  const activeFilters = [filters.category, filters.tag, filters.created_from, filters.sort !== 'newest' ? filters.sort : '', status, search].filter(Boolean).length;
  const setParam = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); setParams(next); };
  const clearFilters = () => { setParams(new URLSearchParams()); setQuery(''); setSearch(''); };
  useEffect(() => { api.get<CampaignOptions>('/campaigns/options').then(r => setFacets(r.data)).catch(() => {}); }, [list.total]);
  useEffect(() => sel.clear(), [status, search, filters.category, filters.tag, filters.sort, filters.created_from]); // eslint-disable-line react-hooks/exhaustive-deps
  const runBulk = async (action: () => Promise<{data: Record<string, number>}>, ok: (r: Record<string, number>) => string) => {
    setError(''); setNotice('');
    try { const r = await action(); setNotice(ok(r.data)); sel.clear(); setBulkDialog(null); await list.reload(true); }
    catch (e) { setError(apiError(e, 'Ação em massa não concluída.')); }
  };
  const bulkDelete = async () => {
    if (!await confirm.ask(`Excluir ${sel.count} produto(s)?`, 'As publicações desses produtos também serão excluídas. Produtos sendo enviados agora ficam de fora.', `Excluir ${sel.count}`)) return;
    runBulk(async () => ({data: await inBatches(sel.ids, chunk => api.post('/products/bulk/delete', {ids: chunk}))}),
      r => `${r.deleted ?? 0} produto(s) excluído(s).${r.skipped ? ` ${r.skipped} em envio ficaram de fora.` : ''}`);
  };
  const bulkUpdate = (body: object, ok: (r: Record<string, number>) => string) =>
    runBulk(async () => ({data: await inBatches(sel.ids, chunk => api.post('/products/bulk/update', {...body, ids: chunk}))}), ok);
  const pageSelected = list.items.length > 0 && list.items.every(p => sel.has(p.id));
  const [original, setOriginal] = useState(''), [affiliate, setAffiliate] = useState(''), [category, setCategory] = useState('');
  const [notice, setNotice] = useState(''), [error, setError] = useState('');
  const [hasExtension, setHasExtension] = useState(false), [capturing, setCapturing] = useState<number | null>(null);
  const [bulk, setBulk] = useState<{done: number; total: number} | null>(null);
  const [editing, setEditing] = useState<Product | null>(null), [draft, setDraft] = useState<Draft | null>(null);
  const [preview, setPreview] = useState<{image_url: string; title: string; message: string} | null>(null);
  const [menu, setMenu] = useState<{anchor: HTMLElement; product: Product} | null>(null);
  const uploadFor = useRef<number | null>(null), fileInput = useRef<HTMLInputElement>(null);
  const autoRead = useRef(new Set<number>());

  useEffect(() => { extensionStatus().then(s => setHasExtension(Boolean(s))); }, []);
  // Enquanto houver produto em extração no servidor, atualiza a lista sozinha.
  const processing = list.items.some(p => p.status === 'processing');
  useEffect(() => { if (!processing) return; const t = setInterval(() => list.reload(true), 4000); return () => clearInterval(t); }, [processing]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (action: () => Promise<unknown>, fallback: string, ok = '') => {
    setError(''); setNotice('');
    try { await action(); if (ok) setNotice(ok); await list.reload(true); return true; }
    catch (e) { setError(apiError(e, fallback)); return false; }
  };

  /** Lê nome, imagem e preços abrindo o produto no navegador (via extensão). */
  const readInBrowser = async (p: Product, quiet = false) => {
    setCapturing(p.id);
    try {
      const data = await captureInBrowser(p.original_url, p.affiliate_url);
      await api.post(`/products/${p.id}/browser-data`, data);
      if (!quiet) setNotice(data.original_price != null ? 'Dados lidos no navegador, com preço anterior.' : 'Dados lidos no navegador. A página não mostra preço anterior.');
      await list.reload(true);
      return true;
    } catch (e) { setError(`${p.title || 'Produto'}: ${apiError(e, 'não consegui ler pelo navegador.')}`); return false; }
    finally { setCapturing(null); }
  };

  // Produtos que só podem ser lidos pelo navegador são lidos assim que aparecem na lista.
  useEffect(() => {
    if (!hasExtension || capturing !== null || bulk) return;
    const next = list.items.find(p => p.status === 'awaiting_browser' && !autoRead.current.has(p.id));
    if (next) { autoRead.current.add(next.id); readInBrowser(next, true); }
  }, [hasExtension, list.items, capturing, bulk]); // eslint-disable-line react-hooks/exhaustive-deps

  const refreshPrices = async () => {
    const targets = list.items.filter(p => browserReadable(p) && isStale(p));
    if (!targets.length) { setNotice(`Todos os preços desta lista foram lidos nas últimas ${STALE_HOURS} h.`); return; }
    setError(''); setNotice(''); setBulk({done: 0, total: targets.length});
    let ok = 0;
    for (const [i, p] of targets.entries()) { if (await readInBrowser(p, true)) ok++; setBulk({done: i + 1, total: targets.length}); }
    setBulk(null); setNotice(`${ok} de ${targets.length} produto(s) com preço atualizado.`);
  };

  const create = () => run(async () => {
    await api.post('/products', {original_url: original.trim(), affiliate_url: affiliate.trim(), category: category.trim()});
    setOriginal(''); setAffiliate('');
  }, 'Falha ao cadastrar o produto.', needsBrowser(original) ? 'Produto cadastrado. A extensão vai ler os dados pelo navegador.' : 'Produto cadastrado. Extraindo dados…');
  const remove = async (p: Product) => {
    if (await confirm.ask('Excluir produto?', `${p.title || 'Este produto'} e as publicações dele serão excluídos.`, 'Excluir')) run(() => api.delete(`/products/${p.id}`), 'Falha ao excluir.', 'Produto excluído.');
  };
  const upload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]; const id = uploadFor.current; event.target.value = '';
    if (!file || !id) return;
    const data = new FormData(); data.append('file', file);
    run(() => api.post(`/products/${id}/image`, data), 'Falha ao processar imagem.', 'Imagem trocada.');
  };
  const saveEdit = async () => {
    if (!editing || !draft) return;
    const price = toNumber(draft.price), originalPrice = toNumber(draft.original_price);
    if ((draft.price.trim() && price === null) || (draft.original_price.trim() && originalPrice === null)) { setError('Preço inválido. Use, por exemplo, 129,90.'); return; }
    if (await run(() => api.patch(`/products/${editing.id}`, {...draft, price, original_price: originalPrice}), 'Falha ao editar.', 'Produto atualizado.')) setEditing(null);
  };
  const field = (key: keyof Draft, label: string, props: object = {}) => draft && <TextField fullWidth label={label} value={draft[key]} onChange={e => setDraft({...draft, [key]: e.target.value})} {...props}/>;
  const setStatusFilter = (value: string) => setParam('status', value);

  return <>
    <PageHeader title="Produtos" description="Tudo o que já foi cadastrado, com o preço lido mais recente de cada um."
      actions={<>{hasExtension && <Button variant="outlined" disabled={Boolean(bulk) || capturing !== null} onClick={refreshPrices}>Atualizar preços</Button>}
        <Tooltip title="Atualizar lista"><IconButton aria-label="Atualizar lista" onClick={() => list.reload()}><RefreshIcon/></IconButton></Tooltip></>}/>

    <Card sx={{mb: 3}}><CardContent>
      <Typography variant="h6" component="h2" mb={0.5}>Cadastrar pelo link</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>Mais rápido: na página do produto, clique no ícone do Autopost na barra do Chrome.</Typography>
      <Grid container spacing={1.5}>
        <Grid item xs={12} md={6}><TextField fullWidth label="Link original do produto" value={original} onChange={e => setOriginal(e.target.value)}
          helperText="A loja é identificada pelo link."/></Grid>
        <Grid item xs={12} md={6}><TextField fullWidth label="Link de afiliado" value={affiliate} onChange={e => setAffiliate(e.target.value)}/></Grid>
        <Grid item xs={12} md={8}><Autocomplete freeSolo options={(facets?.categories ?? []).map(c => c.name)} value={category}
          onInputChange={(_, v) => setCategory(v)} renderInput={params => <TextField {...params} label="Categoria (opcional)"/>}/></Grid>
        <Grid item xs={12} md={4}><Button fullWidth variant="contained" sx={{height: 56}} disabled={!original.trim() || !affiliate.trim()} onClick={create}>Cadastrar produto</Button></Grid>
      </Grid>
    </CardContent></Card>

    <Stack direction={{xs: 'column', sm: 'row'}} gap={1} mb={showFilters ? 1.5 : 2} alignItems={{sm: 'center'}}>
      <TextField size="small" placeholder="Buscar pelo nome" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && setSearch(query)}
        onBlur={() => setSearch(query)} sx={{minWidth: 240}} InputProps={{startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small"/></InputAdornment>}}/>
      <TextField size="small" select label="Status" value={status} onChange={e => setStatusFilter(e.target.value)} sx={{minWidth: 180}}>
        <MenuItem value="">Todos</MenuItem>{productStatuses.map(s => <MenuItem key={s} value={s}>{productLabel(s)[0]}</MenuItem>)}
      </TextField>
      <Badge badgeContent={activeFilters} color="primary"><Button variant={showFilters ? 'contained' : 'outlined'} startIcon={<FilterIcon/>}
        onClick={() => setShowFilters(v => !v)} aria-expanded={showFilters}>Filtros</Button></Badge>
      {activeFilters > 0 && <Button onClick={clearFilters}>Limpar filtros</Button>}
      <Box flex={1}/>
      <Typography variant="body2" color="text.secondary">{list.total} produto(s)</Typography>
    </Stack>
    <Collapse in={showFilters}>
      <Card sx={{p: 2, mb: 2}}><Grid container spacing={1.5}>
        <Grid item xs={12} sm={6} md={3}><TextField select fullWidth size="small" label="Categoria" value={filters.category} onChange={e => setParam('category', e.target.value)}>
          <MenuItem value="">Todas</MenuItem><MenuItem value="__none__">Sem categoria ({facets?.uncategorized ?? 0})</MenuItem>
          {facets?.categories.map(c => <MenuItem key={c.name} value={c.name}>{c.name} ({c.count})</MenuItem>)}</TextField></Grid>
        <Grid item xs={12} sm={6} md={3}><TextField select fullWidth size="small" label="Tag" value={filters.tag} onChange={e => setParam('tag', e.target.value)}>
          <MenuItem value="">Todas</MenuItem>{facets?.tags.map(c => <MenuItem key={c.name} value={c.name}>{c.name} ({c.count})</MenuItem>)}</TextField></Grid>
        <Grid item xs={12} sm={6} md={3}><TextField select fullWidth size="small" label="Ordenar" value={filters.sort} onChange={e => setParam('sort', e.target.value === 'newest' ? '' : e.target.value)}>
          <MenuItem value="newest">Mais recentes</MenuItem><MenuItem value="oldest">Mais antigos</MenuItem><MenuItem value="price_asc">Menor preço</MenuItem>
          <MenuItem value="price_desc">Maior preço</MenuItem><MenuItem value="title">Nome (A a Z)</MenuItem></TextField></Grid>
        <Grid item xs={12} sm={6} md={3}><TextField fullWidth size="small" type="date" label="Cadastrados desde" InputLabelProps={{shrink: true}}
          value={filters.created_from} onChange={e => setParam('from', e.target.value)}/></Grid>
      </Grid></Card>
    </Collapse>
    {list.items.length > 0 && <SelectAll total={list.items.length} selected={list.items.filter(p => sel.has(p.id)).length}
      onAll={() => sel.add(list.items.map(p => p.id))} onNone={sel.clear} label={`Selecionar os ${list.items.length} desta página`}/>}
    <SelectMatching pageCount={list.items.length} pageSelected={pageSelected} selected={sel.count} total={list.total} noun="produtos"
      onSelectAll={async () => sel.setAll(await fetchAllIds('/products', listParams))} onClear={sel.clear}/>

    {!hasExtension && <Alert severity="info" sx={{mb: 2}}>Instale a extensão do Autopost para ler preço anterior e desconto do Mercado Livre pelo seu navegador.</Alert>}
    {bulk && <Box mb={2}><Typography variant="body2" mb={0.5}>Atualizando preços: {bulk.done} de {bulk.total}</Typography><LinearProgress variant="determinate" value={bulk.done * 100 / bulk.total}/></Box>}
    <Feedback error={error || list.error} notice={notice} onRetry={list.error ? () => list.reload() : undefined} onClose={() => { setError(''); setNotice(''); list.setError(''); }}/>
    <Loading show={list.loading}/>
    {!list.loading && !list.items.length && <Empty text="Nenhum produto encontrado."/>}

    <Stack spacing={1.5}>{list.items.map(p => {
      const [label, color] = productLabel(p.status);
      const reading = capturing === p.id || p.status === 'processing';
      return <Card key={p.id} sx={{borderColor: sel.has(p.id) ? 'primary.main' : undefined}}><CardContent sx={{display: 'flex', gap: 2, flexDirection: {xs: 'column', sm: 'row'}, '&:last-child': {pb: 2}}}>
        <Checkbox checked={sel.has(p.id)} onChange={() => sel.toggle(p.id)} sx={{alignSelf: 'flex-start', m: -1}} inputProps={{'aria-label': `Selecionar ${p.title || 'produto'}`}}/>
        {p.image_url ? <Box component="img" src={p.image_url} alt="" sx={{width: 96, height: 96, objectFit: 'contain', borderRadius: 2, flex: 'none', bgcolor: '#fff', border: '1px solid', borderColor: 'divider'}}/>
          : <Box sx={{width: 96, height: 96, borderRadius: 2, bgcolor: 'background.default', flex: 'none'}}/>}
        <Box flex={1} minWidth={0}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography fontWeight={600}>{p.title || (p.status === 'awaiting_browser' ? 'Aguardando leitura no navegador' : reading ? 'Lendo…' : 'Sem nome')}</Typography>
            <Chip size="small" color={color} label={label} icon={reading ? <CircularProgress size={12}/> : undefined}/>
          </Stack>
          <Typography variant="caption" color="text.secondary" noWrap sx={{display: 'block', maxWidth: '100%'}} title={p.original_url}>{p.original_url.replace(/^https?:\/\/(www\.)?/, '')}</Typography>
          <Box my={1}><PriceTag price={p.price} original={p.original_price} note={p.price_note}/></Box>
          <Meta items={[p.store || p.marketplace, p.category,
            <Box component="span" sx={{color: browserReadable(p) && isStale(p) && p.price != null ? 'warning.main' : 'inherit'}}>
              Preço lido {timeAgo(p.captured_at)}{p.data_source === 'browser' ? ' pelo navegador' : p.data_source === 'manual' ? ' (editado à mão)' : ''}</Box>]}/>
          {(p.tags?.length || 0) > 0 && <Stack direction="row" gap={.5} flexWrap="wrap" mt={.75}>{p.tags.map(t =>
            <Chip key={t} size="small" variant="outlined" icon={<TagIcon sx={{fontSize: 14}}/>} label={t} onClick={() => setParam('tag', t)}/>)}</Stack>}
          {p.notes && ['needs_review', 'error', 'awaiting_browser'].includes(p.status) && <Typography variant="caption" color="warning.main" display="block" sx={{whiteSpace: 'pre-wrap'}}>{p.notes}</Typography>}
        </Box>
        <Stack direction={{xs: 'row', sm: 'column'}} spacing={1} alignItems="stretch" sx={{minWidth: 150}}>
          {hasExtension && browserReadable(p)
            ? <Button size="small" variant="outlined" disabled={reading || capturing !== null || Boolean(bulk)} onClick={() => readInBrowser(p)}>{capturing === p.id ? 'Lendo…' : 'Ler no navegador'}</Button>
            : <Button size="small" variant="outlined" disabled={reading} onClick={() => run(() => api.post(`/products/${p.id}/reprocess`), 'Falha ao reprocessar.')}>Reprocessar</Button>}
          <Button size="small" onClick={() => { setEditing(p); setDraft(toDraft(p)); }}>Editar</Button>
          <Button size="small" aria-haspopup="menu" onClick={e => setMenu({anchor: e.currentTarget, product: p})}>Mais</Button>
        </Stack>
      </CardContent></Card>;
    })}</Stack>
    <LoadMore show={list.hasMore} loading={list.loading} onClick={list.loadMore}/>

    <input ref={fileInput} hidden type="file" accept="image/jpeg,image/png,image/webp" onChange={upload}/>
    <Menu anchorEl={menu?.anchor} open={Boolean(menu)} onClose={() => setMenu(null)}>
      <MenuItem onClick={() => { const p = menu!.product; setMenu(null); api.get(`/publications/preview/${p.id}`).then(r => setPreview(r.data)).catch(e => setError(apiError(e, 'Falha na prévia.'))); }}>Ver prévia da mensagem</MenuItem>
      <MenuItem onClick={() => { const p = menu!.product; setMenu(null); uploadFor.current = p.id; fileInput.current?.click(); }}>Trocar imagem</MenuItem>
      {menu && browserReadable(menu.product) && <MenuItem onClick={() => { const p = menu!.product; setMenu(null); run(() => api.post(`/products/${p.id}/reprocess`), 'Falha ao reprocessar.'); }}>Reprocessar</MenuItem>}
      <MenuItem sx={{color: 'error.main'}} onClick={() => { const p = menu!.product; setMenu(null); remove(p); }}>Excluir</MenuItem>
    </Menu>

    <BulkBar count={sel.count} noun="produto(s) selecionado(s)" onClear={sel.clear}>
      <Button size="small" variant="outlined" startIcon={<AddIcon/>} onClick={() => navigate(`/campaigns/new?products=${sel.ids.join(',')}`)}>Adicionar a uma campanha</Button>
      <Button size="small" variant="outlined" onClick={() => { setBulkCategory(''); setBulkDialog('category'); }}>Alterar categoria</Button>
      <Button size="small" variant="outlined" startIcon={<TagIcon/>} onClick={() => { setBulkAdd([]); setBulkRemove([]); setBulkDialog('tags'); }}>Tags</Button>
      <Button size="small" variant="outlined" startIcon={<DeleteIcon/>} onClick={bulkDelete}>Excluir</Button>
    </BulkBar>
    <Dialog open={bulkDialog === 'category'} onClose={() => setBulkDialog(null)} maxWidth="xs" fullWidth>
      <DialogTitle>Alterar categoria de {sel.count} produto(s)</DialogTitle>
      <DialogContent><Autocomplete freeSolo sx={{mt: 1}} options={(facets?.categories ?? []).map(c => c.name)} value={bulkCategory}
        onInputChange={(_, v) => setBulkCategory(v)} renderInput={params => <TextField {...params} label="Nova categoria" helperText="Deixe vazio para remover a categoria."/>}/></DialogContent>
      <DialogActions><Button onClick={() => setBulkDialog(null)}>Cancelar</Button>
        <Button variant="contained" onClick={() => bulkUpdate({category: bulkCategory}, r => `Categoria alterada em ${r.updated ?? 0} produto(s).`)}>Aplicar</Button></DialogActions>
    </Dialog>
    <Dialog open={bulkDialog === 'tags'} onClose={() => setBulkDialog(null)} maxWidth="sm" fullWidth>
      <DialogTitle>Tags de {sel.count} produto(s)</DialogTitle>
      <DialogContent><Stack gap={2} mt={1}>
        <MultiPick label="Adicionar tags" value={bulkAdd} onChange={setBulkAdd} options={facets?.tags ?? []}/>
        <MultiPick label="Remover tags" value={bulkRemove} onChange={setBulkRemove} options={facets?.tags ?? []} free={false}/>
      </Stack></DialogContent>
      <DialogActions><Button onClick={() => setBulkDialog(null)}>Cancelar</Button>
        <Button variant="contained" disabled={!bulkAdd.length && !bulkRemove.length}
          onClick={() => bulkUpdate({add_tags: bulkAdd, remove_tags: bulkRemove}, r => `Tags atualizadas em ${r.updated ?? 0} produto(s).`)}>Aplicar</Button></DialogActions>
    </Dialog>
    {confirm.dialog}

    <Dialog open={Boolean(preview)} onClose={() => setPreview(null)}>
      <DialogTitle>Prévia da mensagem</DialogTitle>
      <DialogContent>{preview && <WhatsAppPreview message={preview.message}/>}</DialogContent>
      <DialogActions><Button onClick={() => setPreview(null)}>Fechar</Button></DialogActions>
    </Dialog>

    <Dialog open={Boolean(editing)} onClose={() => setEditing(null)} maxWidth="md" fullWidth>
      <DialogTitle>Editar produto</DialogTitle>
      <DialogContent><Stack gap={2.5} sx={{pt: 1}}>
        <Box>
          <Typography fontWeight={600} mb={1}>Oferta</Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={12}>{field('title', 'Nome do produto')}</Grid>
            <Grid item xs={6} md={3}>{field('price', 'Preço atual (R$)', {placeholder: '129,90'})}</Grid>
            <Grid item xs={6} md={3}>{field('original_price', 'Preço anterior (R$)', {helperText: 'Vazio = sem "de/por"'})}</Grid>
            <Grid item xs={12} md={6}>{field('price_note', 'Condição do preço', {placeholder: 'no Pix'})}</Grid>
            <Grid item xs={12}>{field('affiliate_url', 'Link de afiliado')}</Grid>
          </Grid>
        </Box>
        <Box>
          <Typography fontWeight={600} mb={1}>Organização</Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={12} md={5}>{draft && <Autocomplete freeSolo options={(facets?.categories ?? []).map(c => c.name)} value={draft.category}
              onInputChange={(_, v) => setDraft({...draft, category: v})} renderInput={params => <TextField {...params} label="Categoria"/>}/>}</Grid>
            <Grid item xs={12} md={7}>{draft && <MultiPick label="Tags" value={draft.tags} onChange={v => setDraft({...draft, tags: v})} options={facets?.tags ?? []}/>}</Grid>
          </Grid>
        </Box>
        <Box>
          <Typography fontWeight={600} mb={1}>Outros dados</Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={6}>{field('store', 'Vendido por (loja)')}</Grid>
            <Grid item xs={6}>{field('marketplace', 'Marketplace', {helperText: 'Preenchido pelo link'})}</Grid>
            <Grid item xs={12}>{field('description', 'Descrição', {multiline: true, minRows: 2})}</Grid>
            <Grid item xs={12}>{field('notes', 'Notas internas', {multiline: true, minRows: 2, helperText: 'Não vão para a mensagem.'})}</Grid>
          </Grid>
        </Box>
      </Stack></DialogContent>
      <DialogActions><Button onClick={() => setEditing(null)}>Cancelar</Button><Button variant="contained" onClick={saveEdit}>Salvar</Button></DialogActions>
    </Dialog>
  </>;
}
