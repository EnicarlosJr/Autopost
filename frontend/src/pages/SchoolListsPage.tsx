// Listas escolares: a lista de material de cada série, com até 3 produtos escolhidos por item.
// A extensão reconfere os preços (no seu Chrome) e a tela gera a página de orçamento para os pais.
import {useCallback, useEffect, useState} from 'react';
import {Link, useNavigate, useParams} from 'react-router-dom';
import {Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, LinearProgress, Stack, Switch,
  Tab, Tabs, TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {captureInBrowser, captureWithAffiliateLink, runSchoolSearch} from '../services/sender';
import type {SchoolItem, SchoolList, SchoolListSummary, SchoolOption, SchoolSearch, SchoolSection, SchoolSuggestion} from '../types/school';
import {Empty, Feedback, Loading} from '../components/Feedback';
import {Meta, PageHeader, PaymentNote, PriceTag} from '../components/Ui';
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

const needsLink = (o: SchoolOption) => !o.has_affiliate_link || o.affiliate_ok === false;

/** Lê o produto e, se faltar (ou não abrir), gera o link de afiliado. Se o link falhar, grava ao menos o preço. */
async function readWithLink(option: SchoolOption): Promise<string> {
  if (!needsLink(option)) { await readProduct(option); return ''; }
  try {
    const data = await captureWithAffiliateLink(option.original_url);
    await api.post(`/products/${option.product_id}/browser-data`, data);
    return '';
  } catch (e) {
    await readProduct(option).catch(() => {});
    return `Produto lido, mas o link de afiliado não foi gerado: ${apiError(e, 'erro na extensão')}`;
  }
}

/** Pede à extensão a busca de equivalentes que estiver na fila (sem esperar: a tela recarrega sozinha). */
function kickSchoolSearch(onDone: () => void) {
  runSchoolSearch().catch(() => null).finally(onDone);
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

/** Convite da página dos pais para quem não tem conta no Mercado Pago: seu WhatsApp e a mensagem pronta. */
function MpHelpCard() {
  const [whatsapp, setWhatsapp] = useState(''), [message, setMessage] = useState(''), [fallback, setFallback] = useState('');
  const [preview, setPreview] = useState(''), [busy, setBusy] = useState(false), [note, setNote] = useState(''), [error, setError] = useState('');
  type Help = {whatsapp: string; message: string; default_message: string; preview_url: string};
  const apply = (d: Help) => { setWhatsapp(d.whatsapp); setMessage(d.message); setFallback(d.default_message); setPreview(d.preview_url); };
  useEffect(() => { api.get<Help>('/school-lists/settings/mp-help').then(r => apply(r.data)).catch(() => {}); }, []);
  const save = async () => {
    setBusy(true); setError(''); setNote('');
    try { apply((await api.put<Help>('/school-lists/settings/mp-help', {whatsapp, message})).data); setNote('Salvo.'); }
    catch (e) { setError(apiError(e, 'Não foi possível salvar.')); }
    finally { setBusy(false); }
  };
  return <Card sx={{p: 2.5, mb: 2}}>
    <Typography fontWeight={700}>Ajuda com o Mercado Pago (página dos pais)</Typography>
    <Typography fontSize={13.5} color="text.secondary" mb={1.5}>Quem responder que não tem conta no Mercado Pago vê o convite "Quero ajuda pelo WhatsApp",
      que abre o WhatsApp da pessoa com a mensagem pronta para o seu número. Sem número, o convite não aparece.</Typography>
    {error && <Alert severity="error" sx={{mb: 1.5}}>{error}</Alert>}
    <Stack direction={{xs: 'column', md: 'row'}} gap={1.5} alignItems={{md: 'flex-start'}}>
      <TextField size="small" label="Seu WhatsApp (com DDD)" placeholder="(11) 99999-0000" value={whatsapp} onChange={e => setWhatsapp(e.target.value)} sx={{minWidth: 220}}/>
      <TextField size="small" label="Mensagem que a pessoa vai enviar" multiline minRows={2} value={message} placeholder={fallback}
        onChange={e => setMessage(e.target.value)} sx={{flex: 1}} inputProps={{maxLength: 600}}
        helperText="Use {escola} e {serie} para o nome da escola e da série. Vazio = a mensagem padrão."/>
      <Stack direction="row" gap={1}>
        <Button variant="contained" disabled={busy} onClick={save}>Salvar</Button>
        {preview && <Button component="a" href={preview} target="_blank" rel="noopener">Testar link</Button>}
      </Stack>
    </Stack>
    {note && <Typography fontSize={13} color="success.main" mt={1}>{note}</Typography>}
  </Card>;
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
      actions={<><Button variant="outlined" component={Link} to="/school-lists/visitors">Responsáveis</Button>
        <Button variant="contained" onClick={() => setOpen(true)}>Nova lista</Button></>}/>
    <Feedback error={error} onRetry={load} onClose={() => setError('')}/>
    <Loading show={loading}/>
    <MpHelpCard/>
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
          l.public ? 'publicada' : 'não publicada', l.visitors > 0 && `${l.visitors} responsável(is)`, l.empty_items > 0 && `${l.empty_items} item(ns) sem produto`, l.missing_links > 0 && `${l.missing_links} opção(ões) sem link de afiliado`]}/></Box>
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
    if (saved) {
      setBusy('Lendo e gerando o link…');
      try { const warning = await readWithLink(saved); if (warning) onError(warning); }
      catch (e) { onError(`Produto salvo, mas a leitura pelo navegador falhou: ${apiError(e, 'erro na extensão')}`); }
      await reload();
      // Com o produto lido, a extensão procura o mesmo produto para as outras opções e um mais barato.
      kickSchoolSearch(() => { reload().catch(() => {}); });
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
    <PaymentNote note={option.price_note} regular={option.regular_price}/>
    {/mercado pago/i.test(option.price_note) && <Typography fontSize={12} color="text.secondary">Na página dos pais, cada um diz se tem conta no Mercado Pago e vê o preço certo.</Typography>}
    {option.price_conditions && <Typography fontSize={12} color="text.secondary">Condições vistas no ML: {option.price_conditions}</Typography>}
    <Meta items={[option.store, ago(option.captured_at), option.price != null && option.buy_qty > 1 && `${option.buy_qty} × = ${brl((option.regular_price && option.regular_price > option.price ? option.regular_price : option.price) * option.buy_qty)}`]}/>
    <Stack direction="row" gap={.75} flexWrap="wrap">
      {option.catalog_id ? <Chip size="small" color="success" variant="outlined" label={`Catálogo ${option.catalog_id}`}/>
        : <Tooltip title="Anúncio sem página de catálogo: o Autopost acompanha só este anúncio, não as outras ofertas do mesmo produto.">
          <Chip size="small" color="warning" variant="outlined" label="Anúncio avulso"/></Tooltip>}
      {option.has_affiliate_link && option.affiliate_ok === false
        ? <Tooltip title="Na última conferência o link meli.la não abriu o produto. A página dos pais usa o link comum (sem comissão) até você gerar de novo.">
          <Chip size="small" color="error" variant="outlined" label="Link não abre"/></Tooltip>
        : <Chip size="small" variant="outlined" color={option.has_affiliate_link ? 'success' : 'warning'}
          label={option.has_affiliate_link ? (option.affiliate_ok ? 'Link de afiliado conferido' : 'Com link de afiliado') : 'Sem link de afiliado'}/>}
      {option.unavailable && <Tooltip title="O Mercado Livre disse que acabou ou pausou. O item continua na lista; esta opção sai da página dos pais até voltar, e o Autopost procura um substituto.">
        <Chip size="small" color="error" label="Indisponível no ML"/></Tooltip>}
    </Stack>
    {option.last_error && <Typography fontSize={12.5} color="error.main">Última conferência falhou: {option.last_error}</Typography>}
    <Stack direction="row" alignItems="center" gap={.5}>
      <Switch size="small" checked={option.watch} onChange={e => patch({watch: e.target.checked})} inputProps={{'aria-label': 'Conferir preço automaticamente'}}/>
      <Typography fontSize={13}>Conferir preço automaticamente</Typography>
    </Stack>
    <Stack direction="row" gap={.75} flexWrap="wrap">
      <Button size="small" variant={stale ? 'contained' : 'outlined'} disabled={Boolean(busy)}
        onClick={() => run('Lendo…', async () => { await readProduct(option); await reload(); onNotice('Preço atualizado.'); })}>{busy === 'Lendo…' ? busy : 'Ler agora'}</Button>
      {needsLink(option) && <Button size="small" variant="outlined" disabled={Boolean(busy)}
        onClick={() => run('Gerando link…', async () => {
          const data = await captureWithAffiliateLink(option.original_url);
          await api.post(`/products/${option.product_id}/browser-data`, data); await reload(); onNotice('Link de afiliado gravado.');
        })}>{busy === 'Gerando link…' ? busy : option.has_affiliate_link ? 'Gerar link de novo' : 'Gerar link de afiliado'}</Button>}
      <Button size="small" disabled={Boolean(busy)} onClick={() => setEditing(true)}>Trocar</Button>
      <Button size="small" color="error" disabled={Boolean(busy)}
        onClick={() => run('Removendo…', async () => onChange((await api.delete<SchoolList>(`/school-lists/items/${item.id}/options/${slot}`)).data))}>Remover</Button>
    </Stack>
  </Box>;
}

const SLOT_NAME = (item: SchoolItem, slot: number) =>
  item.options.find(o => o.slot === slot)?.label || ['Econômica', 'Equilibrada', 'Premium'][slot];

function SuggestionRow({s, action, busy, onUse, onDismiss}: {s: SchoolSuggestion; action: string; busy: boolean; onUse: () => void; onDismiss: () => void}) {
  return <Stack direction={{xs: 'column', sm: 'row'}} gap={1.25} alignItems={{sm: 'center'}} sx={{p: 1, borderRadius: 1.5, border: `1px solid ${tokens.line}`, bgcolor: '#fff'}}>
    <Stack direction="row" gap={1.25} flex={1} minWidth={0} alignItems="center">
      {s.image_url ? <Box component="img" src={s.image_url} alt="" referrerPolicy="no-referrer" sx={{width: 52, height: 52, objectFit: 'contain', borderRadius: 1, flexShrink: 0}}/>
        : <Box sx={{width: 52, height: 52, borderRadius: 1, bgcolor: tokens.paper, flexShrink: 0}}/>}
      <Box minWidth={0}>
        <Typography fontSize={13.5} fontWeight={600} sx={{display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>{s.title}</Typography>
        <Stack direction="row" gap={.5} flexWrap="wrap" mt={.25}>
          {s.signals.map(x => <Chip key={x} size="small" label={x} variant="outlined" sx={{height: 20, fontSize: 11.5}}/>)}
        </Stack>
      </Box>
    </Stack>
    <Stack direction="row" gap={1} alignItems="center" justifyContent="flex-end">
      <Box textAlign="right" maxWidth={240}><PriceTag price={s.price} original={s.original_price} note={s.price_note} size="sm"/>
        <PaymentNote note={s.price_note} regular={s.regular_price}/></Box>
      <Button size="small" variant="contained" disabled={busy} onClick={onUse}>{action}</Button>
      <Button size="small" component="a" href={s.link} target="_blank" rel="noopener">Ver</Button>
      <Button size="small" color="inherit" disabled={busy} onClick={onDismiss}>Descartar</Button>
    </Stack>
  </Stack>;
}

const SEARCH_STATUS: Record<SchoolSearch['status'], string> = {
  queued: 'Na fila: a extensão vai buscar no Mercado Livre pelo seu Chrome.', running: 'Buscando no Mercado Livre pelo seu Chrome…',
  done: '', no_results: 'Nenhum anúncio igual passou na conferência.', failed: 'A busca falhou.',
};

function Suggestions({list, item, onChange, onError, onNotice}: {list: SchoolList; item: SchoolItem; onChange: (l: SchoolList) => void; onError: (m: string) => void; onNotice: (m: string) => void}) {
  const [busy, setBusy] = useState(false);
  const search = item.search;
  const reload = async () => onChange((await api.get<SchoolList>(`/school-lists/${list.id}`)).data);
  const start = async () => {
    setBusy(true);
    try { onChange((await api.post<SchoolList>(`/school-lists/items/${item.id}/search`)).data); kickSchoolSearch(() => { reload().catch(() => {}); }); }
    catch (e) { onError(apiError(e, 'Não foi possível buscar.')); }
    finally { setBusy(false); }
  };
  const use = async (s: SchoolSuggestion, slot: number) => {
    setBusy(true);
    try {
      const r = await api.post<SchoolList>(`/school-lists/items/${item.id}/suggestions/use`, {listing_id: s.listing_id, slot});
      onChange(r.data);
      const option = r.data.items.find(i => i.id === item.id)?.options.find(o => o.slot === slot);
      const warning = option ? await readWithLink(option) : '';
      await reload();
      if (warning) onError(warning); else onNotice(`${SLOT_NAME(item, slot)} preenchida, com link de afiliado.`);
    } catch (e) { onError(apiError(e, 'Não foi possível usar a sugestão.')); }
    finally { setBusy(false); }
  };
  const dismiss = async (s: SchoolSuggestion) => {
    try { onChange((await api.post<SchoolList>(`/school-lists/items/${item.id}/suggestions/dismiss`, {external_id: s.external_id})).data); }
    catch (e) { onError(apiError(e, 'Não foi possível descartar.')); }
  };
  const groups = search ? Object.entries(search.slots).filter(([, rows]) => rows.length).sort(([a], [b]) => Number(a) - Number(b)) : [];
  const reasons = search ? Object.entries(search.reasons).map(([k, v]) => `${k} (${v})`).join(', ') : '';
  const waiting = search && (search.status === 'queued' || search.status === 'running');
  return <Box mt={1.5} sx={{borderTop: `1px dashed ${tokens.line}`, pt: 1.5}}>
    <Stack direction="row" justifyContent="space-between" alignItems="center" gap={1} flexWrap="wrap">
      <Box>
        <Typography fontWeight={700} fontSize={14}>Equivalentes no Mercado Livre</Typography>
        <Typography fontSize={12.5} color="text.secondary">
          {!search ? 'Mesmo produto (medida, quantidade e cor) em outras ofertas e marcas, com nota, vendas e loja conferidas.'
            : SEARCH_STATUS[search.status] || `${search.result_count} anúncios lidos, ${search.accepted} iguais ao item${search.rejected ? `, ${search.rejected} recusados` : ''}.`}
          {search?.error ? ` ${search.error}` : ''}
          {search && search.status !== 'queued' && search.status !== 'running' && reasons ? ` Recusados por: ${reasons}.` : ''}
        </Typography>
      </Box>
      <Button size="small" variant="outlined" disabled={busy || Boolean(waiting)} onClick={start}>{waiting ? 'Buscando…' : search ? 'Buscar de novo' : 'Buscar equivalentes'}</Button>
    </Stack>
    {waiting && <LinearProgress sx={{mt: 1}}/>}
    {groups.map(([slot, rows]) => <Box key={slot} mt={1.25}>
      <Typography fontSize={13} fontWeight={600} mb={.75}>Para a opção {SLOT_NAME(item, Number(slot))} (vazia)</Typography>
      <Stack gap={.75}>{rows.map(s => <SuggestionRow key={s.listing_id} s={s} busy={busy} action={`Usar na ${SLOT_NAME(item, Number(slot))}`}
        onUse={() => use(s, Number(slot))} onDismiss={() => dismiss(s)}/>)}</Stack>
    </Box>)}
    {search && search.cheaper.length > 0 && <Box mt={1.25}>
      <Typography fontSize={13} fontWeight={600} mb={.75} color="success.main">Mais barato que as opções atuais</Typography>
      <Stack gap={.75}>{search.cheaper.map(s => <SuggestionRow key={s.listing_id} s={s} busy={busy} action={`Trocar a ${SLOT_NAME(item, 0)}`}
        onUse={() => use(s, 0)} onDismiss={() => dismiss(s)}/>)}</Stack>
    </Box>}
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
    <Suggestions list={list} item={item} onChange={onChange} onError={onError} onNotice={onNotice}/>
    {confirm.dialog}
  </Card>;
}


/** Dados gravados da lista (PUT exige todos os campos): mistura os atuais com o que mudou. */
function listBody(list: SchoolList, change: Partial<{school: string; grade: string; year: number; public: boolean; contact: string; turmas: string[]}> = {}) {
  return {school: list.school, grade: list.grade, year: list.year, notes: list.notes, refresh_hours: list.refresh_hours,
    public: list.public, contact: list.contact, turmas: list.turmas, ...change};
}

/** Turmas da série: uma etiqueta por turma, com excluir e renomear (clique no nome). */
function TurmasEditor({value, onSave, disabled}: {value: string[]; onSave: (turmas: string[]) => Promise<void>; disabled: boolean}) {
  const [adding, setAdding] = useState(''), [editing, setEditing] = useState<number | null>(null), [draft, setDraft] = useState('');
  const same = (a: string, b: string) => a.trim().toLowerCase() === b.trim().toLowerCase();
  const add = async () => {
    const name = adding.trim();
    if (!name || value.some(t => same(t, name))) { setAdding(''); return; }
    await onSave([...value, name]); setAdding('');
  };
  const rename = async (index: number) => {
    const name = draft.trim();
    setEditing(null);
    if (!name || same(name, value[index])) return;
    await onSave(value.some((t, i) => i !== index && same(t, name)) ? value.filter((_, i) => i !== index)
      : value.map((t, i) => i === index ? name : t));
  };
  return <Box sx={{flex: 1}}>
    <Typography fontSize={13} fontWeight={600} mb={.75}>Turmas desta série</Typography>
    <Stack direction="row" gap={.75} flexWrap="wrap" alignItems="center">
      {value.map((t, i) => editing === i
        ? <TextField key={i} size="small" autoFocus value={draft} onChange={e => setDraft(e.target.value)} sx={{width: 140}}
            onBlur={() => rename(i)} onKeyDown={e => { if (e.key === 'Enter') rename(i); if (e.key === 'Escape') setEditing(null); }}
            inputProps={{'aria-label': `Novo nome da turma ${t}`, maxLength: 60}}/>
        : <Chip key={i} label={t} disabled={disabled} onClick={() => { setEditing(i); setDraft(t); }}
            onDelete={() => onSave(value.filter((_, j) => j !== i))} deleteIcon={<DeleteIcon aria-label={`Excluir turma ${t}`}/>}/>)}
      {!value.length && <Typography fontSize={13} color="text.secondary">Nenhuma: os pais escolhem só a série.</Typography>}
      <TextField size="small" placeholder="Nova turma (ex.: B)" value={adding} onChange={e => setAdding(e.target.value)} sx={{width: 170}}
        onKeyDown={e => { if (e.key === 'Enter') add(); }} inputProps={{maxLength: 60, 'aria-label': 'Nova turma'}}/>
      <Button size="small" disabled={disabled || !adding.trim()} onClick={add}>Adicionar</Button>
    </Stack>
    <Typography fontSize={12} color="text.secondary" mt={.5}>Clique no nome para renomear; o ícone exclui. Quem já se identificou continua na lista de responsáveis.</Typography>
  </Box>;
}

function EditListDialog({list, open, onClose, onChange, onError, onDelete}: {list: SchoolList; open: boolean; onClose: () => void;
  onChange: (l: SchoolList) => void; onError: (m: string) => void; onDelete: () => void}) {
  const [school, setSchool] = useState(list.school), [grade, setGrade] = useState(list.grade), [year, setYear] = useState(list.year), [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setSchool(list.school); setGrade(list.grade); setYear(list.year); } }, [open, list.school, list.grade, list.year]);
  const save = async () => {
    setBusy(true);
    try { onChange((await api.put<SchoolList>(`/school-lists/${list.id}`, listBody(list, {school: school.trim(), grade: grade.trim(), year}))).data); onClose(); }
    catch (e) { onError(apiError(e, 'Não foi possível salvar a lista.')); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
    <DialogTitle>Editar lista</DialogTitle>
    <DialogContent>
      <Stack gap={2} pt={1}>
        <TextField label="Escola" value={school} onChange={e => setSchool(e.target.value)}/>
        <TextField label="Série" required value={grade} onChange={e => setGrade(e.target.value)}/>
        <TextField label="Ano" type="number" value={year} onChange={e => setYear(Number(e.target.value) || year)} inputProps={{min: 2020, max: 2100}}/>
        {list.public && <Alert severity="info">Mudar a escola ou a série muda o link da página dos pais.</Alert>}
      </Stack>
    </DialogContent>
    <DialogActions sx={{justifyContent: 'space-between'}}>
      <Button color="error" onClick={onDelete}>Excluir lista</Button>
      <Box><Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={busy || !grade.trim()} onClick={save}>Salvar</Button></Box>
    </DialogActions>
  </Dialog>;
}

function PublishCard({list, onChange, onError, onNotice}: {list: SchoolList; onChange: (l: SchoolList) => void; onError: (m: string) => void; onNotice: (m: string) => void}) {
  const [contact, setContact] = useState(list.contact), [busy, setBusy] = useState(false);
  useEffect(() => { setContact(list.contact); }, [list.id, list.contact]);
  const save = async (publicValue: boolean) => {
    setBusy(true);
    try {
      const r = await api.put<SchoolList>(`/school-lists/${list.id}`, listBody(list, {public: publicValue, contact: contact.trim()}));
      onChange(r.data); onNotice(publicValue ? 'Página publicada.' : 'Publicação salva.');
    } catch (e) { onError(apiError(e, 'Não foi possível salvar a publicação.')); }
    finally { setBusy(false); }
  };
  const saveTurmas = async (turmas: string[]) => {
    setBusy(true);
    try { onChange((await api.put<SchoolList>(`/school-lists/${list.id}`, listBody(list, {turmas}))).data); onNotice('Turmas salvas.'); }
    catch (e) { onError(apiError(e, 'Não foi possível salvar as turmas.')); }
    finally { setBusy(false); }
  };
  const copy = async () => { try { await navigator.clipboard.writeText(list.public_url); onNotice('Link copiado.'); } catch { onError('Não consegui copiar; selecione o link e copie.'); } };
  return <Card sx={{p: 2, mb: 2}}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} flexWrap="wrap">
      <Box><Typography fontWeight={700}>Página online para os pais</Typography>
        <Typography fontSize={13} color="text.secondary">Os pais informam o nome do aluno e a turma e vão direto para esta lista. {list.visitors} responsável(is) já se identificaram.</Typography></Box>
      <Stack direction="row" alignItems="center" gap={.5}>
        <Switch checked={list.public} disabled={busy} onChange={e => save(e.target.checked)} inputProps={{'aria-label': 'Publicar página'}}/>
        <Typography fontSize={14} fontWeight={600}>{list.public ? 'Publicada' : 'Não publicada'}</Typography>
      </Stack>
    </Stack>
    <Stack direction={{xs: 'column', md: 'row'}} gap={1.5} mt={1.5}>
      <TurmasEditor value={list.turmas} onSave={saveTurmas} disabled={busy}/>
      <TextField size="small" label="Contato para os pais (dados e dúvidas)" value={contact} onChange={e => setContact(e.target.value)} sx={{flex: 1}}
        helperText="Aparece no aviso de autorização. Ex.: e-mail ou WhatsApp."/>
      <Box><Button variant="outlined" disabled={busy} onClick={() => save(list.public)}>Salvar</Button></Box>
    </Stack>
    {list.public && <Stack direction={{xs: 'column', sm: 'row'}} gap={1} alignItems={{sm: 'center'}} mt={1.5}>
      <Typography fontSize={14} sx={{wordBreak: 'break-all'}}>Link para o grupo: <b>{list.public_url}</b></Typography>
      <Button size="small" onClick={copy}>Copiar link</Button>
      <Button size="small" component="a" href={list.public_url} target="_blank" rel="noopener">Abrir página</Button>
    </Stack>}
    {list.public && /localhost|127\.0\.0\.1/.test(list.public_url) && <Alert severity="info" sx={{mt: 1.5}}>
      O link ainda aponta para este computador. Quando o sistema estiver online, defina APP_PUBLIC_URL no .env com o seu domínio.</Alert>}
  </Card>;
}

export function SchoolListEditor() {
  const {id} = useParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [list, setList] = useState<SchoolList | null>(null), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [section, setSection] = useState<SchoolSection>('coletivo'), [paste, setPaste] = useState(''), [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{done: number; total: number} | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const apply = (l: SchoolList) => setList(l);
  const load = useCallback(async () => {
    try { apply((await api.get<SchoolList>(`/school-lists/${id}`)).data); setError(''); }
    catch (e) { setError(apiError(e, 'Não foi possível carregar a lista.')); }
  }, [id]);
  useEffect(() => { load(); }, [load]);
  // Enquanto alguma busca de equivalentes está na fila, recarrega a cada 10 s para mostrar as sugestões.
  const searching = Boolean(list?.items.some(i => i.search && (i.search.status === 'queued' || i.search.status === 'running')));
  useEffect(() => {
    if (!searching) return;
    const timer = window.setInterval(() => { load(); }, 10000);
    return () => window.clearInterval(timer);
  }, [searching, load]);
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
  const linkAll = async () => {
    const options = list.items.flatMap(i => i.options).filter(needsLink);
    const unique = [...new Map(options.map(o => [o.product_id, o])).values()];
    setProgress({done: 0, total: unique.length});
    let failed = 0;
    for (const [n, option] of unique.entries()) {
      if (await readWithLink(option).catch(() => 'erro')) failed++;
      setProgress({done: n + 1, total: unique.length});
    }
    setProgress(null); await load();
    setNotice(failed ? `Links gerados. ${failed} produto(s) ficaram sem link: confira se você está logado como afiliado no Chrome.` : 'Todos os links de afiliado foram gerados.');
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
        <Button onClick={() => setEditOpen(true)}>Editar lista</Button>
        <Button variant="outlined" disabled={Boolean(progress)} onClick={refreshAll}>Atualizar todos os preços</Button>
        <Button variant="contained" onClick={download}>Baixar página de orçamento</Button>
      </>}/>
    <Feedback error={error} notice={notice} onClose={() => { setError(''); setNotice(''); }}/>
    {progress && <Box mb={2}><Typography fontSize={13} mb={.5}>Lendo no seu Chrome: {progress.done} de {progress.total}</Typography>
      <LinearProgress variant="determinate" value={progress.total ? progress.done * 100 / progress.total : 0}/></Box>}
    <Card sx={{p: 2, mb: 2}}>
      <Stack direction={{xs: 'column', md: 'row'}} gap={2} justifyContent="space-between">
        <Box><Typography fontWeight={700}>Coletivo</Typography><Typography fontSize={14}>{range(list.totals.coletivo)}</Typography></Box>
        <Box><Typography fontWeight={700}>Individual</Typography><Typography fontSize={14}>{range(list.totals.individual)}</Typography></Box>
        <Box><Typography fontWeight={700}>Conferência automática</Typography>
          <Typography fontSize={14}>A cada {list.refresh_hours} h, pela extensão · {ago(list.oldest_capture).replace('conferido', 'mais antigo')}</Typography></Box>
      </Stack>
      {(list.missing_links > 0 || list.broken_links > 0 || list.empty_items > 0 || list.unavailable > 0) && <Alert severity="warning" sx={{mt: 1.5}}
        action={(list.missing_links > 0 || list.broken_links > 0) ? <Button color="inherit" size="small" disabled={Boolean(progress)} onClick={linkAll}>Gerar links que faltam</Button> : undefined}>
        {list.empty_items > 0 && `${list.empty_items} item(ns) ainda sem produto. `}
        {list.missing_links > 0 && `${list.missing_links} opção(ões) sem link de afiliado: na página dos pais elas usam o link comum, sem comissão. `}
        {list.broken_links > 0 && `${list.broken_links} link(s) de afiliado não abriram o produto na última conferência. `}
        {list.unavailable > 0 && `${list.unavailable} opção(ões) indisponíveis no Mercado Livre: saem da página dos pais e o Autopost procura substitutos.`}
      </Alert>}
      {list.suggestions > 0 && <Alert severity="info" sx={{mt: 1.5}}>{list.suggestions} item(ns) com sugestões de equivalentes ou de um produto mais barato. Confira em cada item.</Alert>}
    </Card>
    <PublishCard list={list} onChange={apply} onError={setError} onNotice={setNotice}/>
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
    <EditListDialog list={list} open={editOpen} onClose={() => setEditOpen(false)} onChange={apply} onError={setError}
      onDelete={() => { setEditOpen(false); removeList(); }}/>
    {confirm.dialog}
  </>;
}
