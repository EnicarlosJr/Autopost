// Listas escolares: a lista de material de cada série, com até 3 produtos escolhidos por item.
// A extensão reconfere os preços (no seu Chrome) e a tela gera a página de orçamento para os pais.
import {useCallback, useEffect, useState} from 'react';
import {Link, useNavigate, useParams} from 'react-router-dom';
import {Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, LinearProgress, Stack, Switch,
  Tab, Tabs, TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {captureInBrowser, captureWithAffiliateLink} from '../services/sender';
import type {SchoolItem, SchoolList, SchoolListSummary, SchoolOption, SchoolSection} from '../types/school';
import {Empty, Feedback, Loading} from '../components/Feedback';
import {Meta, PageHeader, PriceTag} from '../components/Ui';
import {useConfirm} from '../components/Bulk';
import {DeleteIcon} from '../components/Icons';
import {tokens} from '../theme';

const brl = (n: number) => n.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
const SECTION_LABEL: Record<SchoolSection, string> = {coletivo: 'Coletivo (vai para a escola)', individual: 'Individual (fica com a criança)'};
const SLOTS = [0, 1, 2];

function ago(iso: string | null): string {
  if (!iso) return 'preço ainda não lido';
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (minutes < 60) return `conferido há ${Math.max(1, minutes)} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `conferido há ${hours} h` : `conferido há ${Math.round(hours / 24)} dias`;
}

function range(t?: {min: number; max: number; items: number; priced: number}) {
  if (!t || !t.items) return 'sem itens';
  const money = t.min === t.max ? brl(t.min) : `${brl(t.min)} a ${brl(t.max)}`;
  return `${money} · ${t.priced} de ${t.items} itens com preço`;
}

/** Lê o produto no Chrome (nome, foto e preço) e grava no Autopost. */
async function readProduct(option: {product_id: number; original_url: string; affiliate_url: string}) {
  const data = await captureInBrowser(option.original_url, option.affiliate_url);
  await api.post(`/products/${option.product_id}/browser-data`, data);
}

// ------------------------------------------------------------------ lista das listas

function NewListDialog({open, onClose, onCreated}: {open: boolean; onClose: () => void; onCreated: (id: number) => void}) {
  const [school, setSchool] = useState(''), [grade, setGrade] = useState(''), [year, setYear] = useState(new Date().getFullYear() + 1);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const create = async () => {
    setBusy(true); setError('');
    try { const r = await api.post<SchoolList>('/school-lists', {school, grade, year}); onCreated(r.data.id); }
    catch (e) { setError(apiError(e, 'Não foi possível criar a lista.')); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
    <DialogTitle>Nova lista escolar</DialogTitle>
    <DialogContent>
      {error && <Alert severity="error" sx={{mb: 2}}>{error}</Alert>}
      <Stack gap={2} pt={1}>
        <TextField label="Escola" value={school} onChange={e => setSchool(e.target.value)} placeholder="Ex.: Colégio CPCM"/>
        <TextField label="Série" required value={grade} onChange={e => setGrade(e.target.value)} placeholder="Ex.: Maternal II"/>
        <TextField label="Ano" type="number" value={year} onChange={e => setYear(Number(e.target.value) || year)} inputProps={{min: 2020, max: 2100}}/>
      </Stack>
    </DialogContent>
    <DialogActions><Button onClick={onClose}>Cancelar</Button>
      <Button variant="contained" disabled={busy || !grade.trim()} onClick={create}>Criar lista</Button></DialogActions>
  </Dialog>;
}

export function SchoolListsPage() {
  const [lists, setLists] = useState<SchoolListSummary[]>([]), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const load = useCallback(async () => {
    setLoading(true);
    try { setLists((await api.get<SchoolListSummary[]>('/school-lists')).data); setError(''); }
    catch (e) { setError(apiError(e, 'Não foi possível carregar as listas.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  return <>
    <PageHeader title="Listas escolares" description="A lista de material de cada série, com os produtos que você escolheu para cada item. O Autopost reconfere os preços e gera a página de orçamento para os pais."
      actions={<Button variant="contained" onClick={() => setOpen(true)}>Nova lista</Button>}/>
    <Feedback error={error} onRetry={load} onClose={() => setError('')}/>
    <Loading show={loading}/>
    {!loading && !lists.length && <Empty text="Nenhuma lista ainda. Crie a primeira com a série e cole os itens da lista da escola."/>}
    <Stack gap={1.5}>
      {lists.map(l => <Card key={l.id} component={Link} to={`/school-lists/${l.id}`} sx={{p: 2.5, textDecoration: 'none', color: 'inherit', '&:hover': {borderColor: tokens.ink}}}>
        <Stack direction={{xs: 'column', sm: 'row'}} justifyContent="space-between" gap={1}>
          <Box>
            <Typography fontWeight={700} fontSize={17}>{l.grade} · {l.year}</Typography>
            <Typography color="text.secondary" fontSize={14}>{l.school || 'Escola não informada'}</Typography>
          </Box>
          <Stack alignItems={{sm: 'flex-end'}} gap={.5}>
            <Typography fontSize={14}><b>Coletivo:</b> {range(l.totals.coletivo)}</Typography>
            <Typography fontSize={14}><b>Individual:</b> {range(l.totals.individual)}</Typography>
          </Stack>
        </Stack>
        <Box mt={1}><Meta items={[ago(l.oldest_capture).replace('conferido', 'preço mais antigo conferido'),
          l.empty_items > 0 && `${l.empty_items} item(ns) sem produto`, l.missing_links > 0 && `${l.missing_links} opção(ões) sem link de afiliado`]}/></Box>
      </Card>)}
    </Stack>
    <NewListDialog open={open} onClose={() => setOpen(false)} onCreated={id => navigate(`/school-lists/${id}`)}/>
  </>;
}

// ------------------------------------------------------------------ editor

function OptionCard({list, item, slot, option, onChange, onError, onNotice}: {list: SchoolList; item: SchoolItem; slot: number; option?: SchoolOption;
  onChange: (list: SchoolList) => void; onError: (m: string) => void; onNotice: (m: string) => void}) {
  const [url, setUrl] = useState(''), [busy, setBusy] = useState(''), [editing, setEditing] = useState(false);
  const run = async (label: string, job: () => Promise<void>) => {
    setBusy(label);
    try { await job(); } catch (e) { onError(apiError(e, 'Não foi possível concluir.')); } finally { setBusy(''); }
  };
  const reload = async () => onChange((await api.get<SchoolList>(`/school-lists/${list.id}`)).data);
  const save = () => run('Lendo o produto…', async () => {
    const r = await api.put<SchoolList & {product_id: number}>(`/school-lists/items/${item.id}/options/${slot}`,
      {url: url.trim(), label: option?.label || '', buy_qty: option?.buy_qty || 1, watch: option?.watch ?? true});
    onChange(r.data); setUrl(''); setEditing(false);
    const saved = r.data.items.find(i => i.id === item.id)?.options.find(o => o.slot === slot);
    if (saved && saved.price == null) {
      try { await readProduct(saved); await reload(); }
      catch (e) { onError(`Produto salvo, mas a leitura pelo navegador falhou: ${apiError(e, 'erro na extensão')}`); }
    }
  });
  const patch = (body: Partial<SchoolOption>) => run('Salvando…', async () => {
    onChange((await api.patch<SchoolList>(`/school-lists/items/${item.id}/options/${slot}`, body)).data);
  });
  if (!option || editing) return <Box sx={{border: `1px dashed ${tokens.line}`, borderRadius: 2, p: 1.5, display: 'grid', gap: 1, alignContent: 'start'}}>
    <Typography fontWeight={600} fontSize={13}>{option ? `Trocar opção ${slot + 1}` : `Opção ${slot + 1} (vazia)`}</Typography>
    <TextField size="small" label="Link do anúncio no Mercado Livre" value={url} onChange={e => setUrl(e.target.value)}
      helperText="Prefira a página de catálogo (/p/MLB…): o ML mostra nela a melhor oferta do mesmo produto."/>
    <Stack direction="row" gap={1}>
      <Button size="small" variant="contained" disabled={!/^https?:\/\//.test(url.trim()) || Boolean(busy)} onClick={save}>{busy || 'Salvar e ler produto'}</Button>
      {editing && <Button size="small" onClick={() => setEditing(false)}>Cancelar</Button>}
    </Stack>
  </Box>;
  const stale = !option.captured_at;
  return <Box sx={{border: `1px solid ${tokens.line}`, borderRadius: 2, p: 1.5, display: 'grid', gap: 1, alignContent: 'start', bgcolor: '#fff'}}>
    <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1}>
      <TextField size="small" variant="standard" value={option.label} inputProps={{'aria-label': 'Nome da opção', maxLength: 40}}
        onChange={e => onChange(replaceOption(list, item, slot, {label: e.target.value}))} onBlur={e => patch({label: e.target.value})} sx={{maxWidth: 140}}/>
      <TextField size="small" type="number" label="Qtd." value={option.buy_qty} sx={{width: 72}} inputProps={{min: 1, max: 999}}
        onChange={e => onChange(replaceOption(list, item, slot, {buy_qty: Math.max(1, Number(e.target.value) || 1)}))}
        onBlur={e => patch({buy_qty: Math.max(1, Number(e.target.value) || 1)})}/>
    </Stack>
    <Stack direction="row" gap={1.25}>
      {option.image_url
        ? <Box component="img" src={option.image_url} alt="" sx={{width: 72, height: 72, objectFit: 'contain', borderRadius: 1.5, border: `1px solid ${tokens.line}`, flexShrink: 0, bgcolor: '#fff'}}/>
        : <Box sx={{width: 72, height: 72, borderRadius: 1.5, bgcolor: tokens.paper, flexShrink: 0}}/>}
      <Box minWidth={0}>
        <Typography fontSize={13.5} fontWeight={600} sx={{display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>
          {option.title || 'Aguardando leitura do produto'}</Typography>
        <PriceTag price={option.price} original={option.original_price} note={option.price_note} size="sm"/>
      </Box>
    </Stack>
    <Meta items={[option.store, ago(option.captured_at), option.price != null && option.buy_qty > 1 && `${option.buy_qty} × = ${brl(option.price * option.buy_qty)}`]}/>
    <Stack direction="row" gap={.75} flexWrap="wrap">
      {option.catalog_id ? <Chip size="small" color="success" variant="outlined" label={`Catálogo ${option.catalog_id}`}/>
        : <Tooltip title="Anúncio sem página de catálogo: o Autopost acompanha só este anúncio, não as outras ofertas do mesmo produto.">
          <Chip size="small" color="warning" variant="outlined" label="Anúncio avulso"/></Tooltip>}
      <Chip size="small" variant="outlined" color={option.has_affiliate_link ? 'success' : 'warning'}
        label={option.has_affiliate_link ? 'Com link de afiliado' : 'Sem link de afiliado'}/>
    </Stack>
    {option.last_error && <Typography fontSize={12.5} color="error.main">Última conferência falhou: {option.last_error}</Typography>}
    <Stack direction="row" alignItems="center" gap={.5}>
      <Switch size="small" checked={option.watch} onChange={e => patch({watch: e.target.checked})} inputProps={{'aria-label': 'Conferir preço automaticamente'}}/>
      <Typography fontSize={13}>Conferir preço automaticamente</Typography>
    </Stack>
    <Stack direction="row" gap={.75} flexWrap="wrap">
      <Button size="small" variant={stale ? 'contained' : 'outlined'} disabled={Boolean(busy)}
        onClick={() => run('Lendo…', async () => { await readProduct(option); await reload(); onNotice('Preço atualizado.'); })}>{busy === 'Lendo…' ? busy : 'Ler agora'}</Button>
      {!option.has_affiliate_link && <Button size="small" variant="outlined" disabled={Boolean(busy)}
        onClick={() => run('Gerando link…', async () => {
          const data = await captureWithAffiliateLink(option.original_url);
          await api.post(`/products/${option.product_id}/browser-data`, data); await reload(); onNotice('Link de afiliado gravado.');
        })}>{busy === 'Gerando link…' ? busy : 'Gerar link de afiliado'}</Button>}
      <Button size="small" disabled={Boolean(busy)} onClick={() => setEditing(true)}>Trocar</Button>
      <Button size="small" color="error" disabled={Boolean(busy)}
        onClick={() => run('Removendo…', async () => onChange((await api.delete<SchoolList>(`/school-lists/items/${item.id}/options/${slot}`)).data))}>Remover</Button>
    </Stack>
  </Box>;
}

function replaceOption(list: SchoolList, item: SchoolItem, slot: number, change: Partial<SchoolOption>): SchoolList {
  return {...list, items: list.items.map(i => i.id !== item.id ? i : {...i, options: i.options.map(o => o.slot === slot ? {...o, ...change} : o)})};
}

function ItemCard({list, item, onChange, onError, onNotice}: {list: SchoolList; item: SchoolItem; onChange: (l: SchoolList) => void; onError: (m: string) => void; onNotice: (m: string) => void}) {
  const confirm = useConfirm();
  const [name, setName] = useState(item.name), [requested, setRequested] = useState(item.requested), [color, setColor] = useState(item.color);
  useEffect(() => { setName(item.name); setRequested(item.requested); setColor(item.color); }, [item.name, item.requested, item.color]);
  const save = async (body: Record<string, string>) => {
    try { onChange((await api.patch<SchoolList>(`/school-lists/items/${item.id}`, body)).data); }
    catch (e) { onError(apiError(e, 'Não foi possível salvar o item.')); }
  };
  const remove = async () => {
    if (!await confirm.ask('Excluir item?', `"${item.name}" e as opções escolhidas saem da lista. Os produtos continuam em Produtos.`, 'Excluir item')) return;
    try { onChange((await api.delete<SchoolList>(`/school-lists/items/${item.id}`)).data); } catch (e) { onError(apiError(e, 'Não foi possível excluir.')); }
  };
  const bySlot = new Map(item.options.map(o => [o.slot, o]));
  return <Card sx={{p: 2}}>
    <Stack direction={{xs: 'column', md: 'row'}} gap={1.5} alignItems={{md: 'center'}} mb={1.5}>
      <TextField size="small" label="Item" value={name} onChange={e => setName(e.target.value)} onBlur={() => name.trim() && name !== item.name && save({name})} sx={{flex: 2}}/>
      <TextField size="small" label="Como a escola pede" value={requested} placeholder="Ex.: 2 unidades" onChange={e => setRequested(e.target.value)}
        onBlur={() => requested !== item.requested && save({requested})} sx={{flex: 1}}/>
      <TextField size="small" label="Cor" value={color} onChange={e => setColor(e.target.value)} onBlur={() => color !== item.color && save({color})} sx={{flex: 1}}/>
      <IconButton aria-label={`Excluir ${item.name}`} onClick={remove}><DeleteIcon/></IconButton>
    </Stack>
    <Box sx={{display: 'grid', gridTemplateColumns: {xs: '1fr', md: 'repeat(3, minmax(0, 1fr))'}, gap: 1.5}}>
      {SLOTS.map(slot => <OptionCard key={slot} list={list} item={item} slot={slot} option={bySlot.get(slot)} onChange={onChange} onError={onError} onNotice={onNotice}/>)}
    </Box>
    {confirm.dialog}
  </Card>;
}

export function SchoolListEditor() {
  const {id} = useParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [list, setList] = useState<SchoolList | null>(null), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [section, setSection] = useState<SchoolSection>('coletivo'), [paste, setPaste] = useState(''), [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{done: number; total: number} | null>(null);
  const apply = (l: SchoolList) => setList(l);
  const load = useCallback(async () => {
    try { apply((await api.get<SchoolList>(`/school-lists/${id}`)).data); setError(''); }
    catch (e) { setError(apiError(e, 'Não foi possível carregar a lista.')); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  if (!list) return <><Feedback error={error} onRetry={load} onClose={() => setError('')}/><Loading show={!error}/></>;

  const items = list.items.filter(i => i.section === section);
  const importItems = async () => {
    setBusy(true);
    try {
      const r = await api.post<SchoolList & {imported: number}>(`/school-lists/${list.id}/items/import`, {section, text: paste});
      apply(r.data); setPaste(''); setNotice(`${r.data.imported} item(ns) adicionados.`);
    } catch (e) { setError(apiError(e, 'Não foi possível importar os itens.')); }
    finally { setBusy(false); }
  };
  const refreshAll = async () => {
    const options = list.items.flatMap(i => i.options);
    const unique = [...new Map(options.map(o => [o.product_id, o])).values()];
    setProgress({done: 0, total: unique.length});
    let failed = 0;
    for (const [n, option] of unique.entries()) {
      try { await readProduct(option); } catch { failed++; }
      setProgress({done: n + 1, total: unique.length});
    }
    setProgress(null); await load();
    setNotice(failed ? `Preços atualizados. ${failed} produto(s) não puderam ser lidos.` : 'Todos os preços foram atualizados.');
  };
  const download = async () => {
    try {
      const r = await api.get(`/school-lists/${list.id}/page.html`, {responseType: 'blob'});
      const href = URL.createObjectURL(r.data as Blob);
      const a = document.createElement('a');
      a.href = href; a.download = `orcamento-${list.grade}-${list.year}.html`.toLowerCase().replace(/\s+/g, '-');
      a.click(); setTimeout(() => URL.revokeObjectURL(href), 2000);
    } catch (e) { setError(apiError(e, 'Não foi possível gerar a página.')); }
  };
  const removeList = async () => {
    if (!await confirm.ask('Excluir lista?', `A lista de ${list.grade} ${list.year} e os itens saem do Autopost. Os produtos continuam em Produtos.`, 'Excluir lista')) return;
    try { await api.delete(`/school-lists/${list.id}`); navigate('/school-lists'); } catch (e) { setError(apiError(e, 'Não foi possível excluir.')); }
  };

  return <>
    <PageHeader title={`${list.grade} · ${list.year}`} description={<>{list.school || 'Escola não informada'} · <Link to="/school-lists">todas as listas</Link></>}
      actions={<>
        <Button variant="outlined" disabled={Boolean(progress)} onClick={refreshAll}>Atualizar todos os preços</Button>
        <Button variant="contained" onClick={download}>Baixar página de orçamento</Button>
      </>}/>
    <Feedback error={error} notice={notice} onClose={() => { setError(''); setNotice(''); }}/>
    {progress && <Box mb={2}><Typography fontSize={13} mb={.5}>Lendo preços no seu Chrome: {progress.done} de {progress.total}</Typography>
      <LinearProgress variant="determinate" value={progress.total ? progress.done * 100 / progress.total : 0}/></Box>}
    <Card sx={{p: 2, mb: 2}}>
      <Stack direction={{xs: 'column', md: 'row'}} gap={2} justifyContent="space-between">
        <Box><Typography fontWeight={700}>Coletivo</Typography><Typography fontSize={14}>{range(list.totals.coletivo)}</Typography></Box>
        <Box><Typography fontWeight={700}>Individual</Typography><Typography fontSize={14}>{range(list.totals.individual)}</Typography></Box>
        <Box><Typography fontWeight={700}>Conferência automática</Typography>
          <Typography fontSize={14}>A cada {list.refresh_hours} h, pela extensão · {ago(list.oldest_capture).replace('conferido', 'mais antigo')}</Typography></Box>
      </Stack>
      {(list.missing_links > 0 || list.empty_items > 0) && <Alert severity="warning" sx={{mt: 1.5}}>
        {list.empty_items > 0 && `${list.empty_items} item(ns) ainda sem produto. `}
        {list.missing_links > 0 && `${list.missing_links} opção(ões) sem link de afiliado: na página dos pais elas usam o link comum, sem comissão.`}
      </Alert>}
    </Card>
    <Tabs value={section} onChange={(_, v) => setSection(v)} sx={{mb: 2}}>
      {(['coletivo', 'individual'] as SchoolSection[]).map(s => <Tab key={s} value={s}
        label={`${SECTION_LABEL[s]} (${list.items.filter(i => i.section === s).length})`}/>)}
    </Tabs>
    <Card sx={{p: 2, mb: 2}}>
      <Typography fontWeight={600} mb={1}>Adicionar itens ao {section}</Typography>
      <TextField multiline minRows={3} fullWidth value={paste} onChange={e => setPaste(e.target.value)}
        placeholder={'Cole a lista da escola, um item por linha. Ex.:\n2 Colas brancas 90 g\nFolhas de ofício | 500 folhas'}/>
      <Box mt={1}><Button variant="contained" disabled={busy || !paste.trim()} onClick={importItems}>Adicionar itens</Button></Box>
    </Card>
    {!items.length && <Empty text="Nenhum item nesta parte da lista ainda."/>}
    <Stack gap={2}>
      {items.map(item => <ItemCard key={item.id} list={list} item={item} onChange={apply} onError={setError} onNotice={setNotice}/>)}
    </Stack>
    <Box mt={4}><Button color="error" onClick={removeList}>Excluir esta lista</Button></Box>
    {confirm.dialog}
  </>;
}
