import {useCallback, useEffect, useRef, useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Alert, Badge, Box, Button, Card, CardContent, Checkbox, Chip, Collapse, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, InputAdornment, MenuItem, Stack, Switch, Tab, Tabs, TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {extensionStatus, sendPublication, setAutoSend, testSendInWhatsApp, type ExtensionStatus} from '../services/sender';
import type {Product, Publication, Summary} from '../types/models';
import {publicationLabel, timeAgo, toLocalInput} from '../labels';
import {usePaged} from '../hooks/usePaged';
import {Empty, Feedback, Loading, LoadMore} from '../components/Feedback';
import WhatsAppPreview from '../components/WhatsAppPreview';
import {Meta, PageHeader, PriceTag} from '../components/Ui';
import {BulkBar, ExpandAll, SelectAll, useConfirm} from '../components/Bulk';
import {RefreshIcon, SearchIcon} from '../components/Icons';
import type {Campaign} from '../types/campaign';

const TABS: [string, string][] = [['awaiting_approval', 'Aguardando aprovação'], ['approved', 'Prontas'], ['scheduled', 'Agendadas'], ['paused', 'Pausadas'],
  ['failed', 'Falhas'], ['sent', 'Enviadas'], ['cancelled', 'Canceladas']];
const EDITABLE = ['pending', 'awaiting_approval', 'approved', 'scheduled', 'failed'];
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

type SendChoice = 'default' | 'preview' | 'image';
type Draft = {id?: number; product_id: string; group_name: string; scheduled: string; message: string; force_repost: boolean; send_mode: SendChoice};

function PublicationDialog({draft, onClose, onSaved, onError}: {draft: Draft | null; onClose: () => void; onSaved: (text: string) => void; onError: (text: string) => void}) {
  const [value, setValue] = useState<Draft | null>(draft), [products, setProducts] = useState<Product[]>([]), [busy, setBusy] = useState(false);
  useEffect(() => { setValue(draft); }, [draft]);
  useEffect(() => { if (draft && !draft.id) api.get<Product[]>('/products', {params: {status: 'processed', limit: 200}}).then(r => setProducts(r.data)).catch(() => {}); }, [draft]);
  if (!value) return null;
  const set = (patch: Partial<Draft>) => setValue({...value, ...patch});
  const loadStandard = () => api.get(`/publications/preview/${value.product_id}`).then(r => set({message: r.data.message})).catch(e => onError(apiError(e, 'Falha ao gerar o texto padrão.')));
  const save = async () => {
    setBusy(true);
    try {
      const scheduled = value.scheduled ? new Date(value.scheduled).toISOString() : null;
      if (value.id) {
        await api.patch(`/publications/${value.id}`, {message: value.message, group_name: value.group_name, send_mode: value.send_mode, ...(scheduled ? {scheduled_at: scheduled} : {clear_schedule: true})});
        onSaved('Publicação atualizada.');
      } else {
        const message = value.message || (await api.get(`/publications/preview/${value.product_id}`)).data.message;
        await api.post('/publications', {product_id: Number(value.product_id), message, group_name: value.group_name, scheduled_at: scheduled, force_repost: value.force_repost,
          send_mode: value.send_mode === 'default' ? null : value.send_mode});
        onSaved('Publicação criada.');
      }
    } catch (e) { onError(apiError(e, 'Não foi possível salvar a publicação.')); }
    finally { setBusy(false); }
  };
  return <Dialog open onClose={onClose} maxWidth="md" fullWidth>
    <DialogTitle>{value.id ? 'Editar publicação' : 'Nova publicação'}</DialogTitle>
    <DialogContent><Stack spacing={2} sx={{pt: 1}}>
      {!value.id && <TextField select label="Produto" value={value.product_id} onChange={e => set({product_id: e.target.value, message: ''})}>
        <MenuItem value="">Selecione</MenuItem>{products.map(p => <MenuItem value={String(p.id)} key={p.id}>{p.title || `Produto ${p.id}`}</MenuItem>)}
      </TextField>}
      <TextField label="Grupo do WhatsApp (nome exato)" value={value.group_name} onChange={e => set({group_name: e.target.value})}/>
      <TextField select label="Forma de envio" value={value.send_mode} onChange={e => set({send_mode: e.target.value as SendChoice})}
        helperText="Padrão = o da campanha ou, para ofertas avulsas, o das Configurações.">
        <MenuItem value="default">Padrão</MenuItem>
        <MenuItem value="preview">Texto com prévia do link</MenuItem>
        <MenuItem value="image">Foto + texto</MenuItem>
      </TextField>
      <TextField type="datetime-local" label="Agendar (vazio = enviar quando estiver pronta)" InputLabelProps={{shrink: true}} value={value.scheduled} onChange={e => set({scheduled: e.target.value})}/>
      <TextField multiline minRows={8} label={value.id ? 'Mensagem' : 'Mensagem (vazio usa o modelo das Configurações)'} value={value.message} onChange={e => set({message: e.target.value})}/>
      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
        <Button size="small" disabled={!value.product_id} onClick={loadStandard}>{value.id ? 'Substituir pelo texto padrão atual' : 'Carregar texto padrão para editar'}</Button>
        {!value.id && <FormControlLabel control={<Checkbox size="small" checked={value.force_repost} onChange={e => set({force_repost: e.target.checked})}/>} label="Repostar mesmo se enviado recentemente"/>}
      </Stack>
    </Stack></DialogContent>
    <DialogActions><Button onClick={onClose}>Cancelar</Button><Button variant="contained" disabled={busy || !value.product_id || (Boolean(value.id) && !value.message.trim())} onClick={save}>Salvar</Button></DialogActions>
  </Dialog>;
}

export default function QueuePage() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([key]) => key === params.get('tab')) ? params.get('tab')! : 'awaiting_approval';
  const group = params.get('group') || '', campaign = params.get('campaign') || '';
  const [query, setQuery] = useState(''), [search, setSearch] = useState('');
  const list = usePaged<Publication>('/publications', {status: tab, group_name: group || undefined, campaign_id: campaign || undefined, q: search || undefined});
  const [groups, setGroups] = useState<string[]>([]), [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [expanded, setExpanded] = useState<number[]>([]);
  const confirm = useConfirm();
  useEffect(() => {
    api.get<{group_name: string}[]>('/group-schedules').then(r => setGroups(r.data.map(g => g.group_name))).catch(() => {});
    api.get<Campaign[]>('/campaigns').then(r => setCampaigns(r.data)).catch(() => {});
  }, []);
  const setParam = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); setParams(next); };
  const [summary, setSummary] = useState<Summary>({}), [ext, setExt] = useState<ExtensionStatus | null>(null);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [checked, setChecked] = useState<number[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null), [busy, setBusy] = useState<number | null>(null);
  const [running, setRunning] = useState(false), [countdown, setCountdown] = useState(0), [progress, setProgress] = useState('');
  const [openChat, setOpenChat] = useState(() => localStorage.getItem('autopost_open_chat') === '1');
  const [interval, setIntervalSeconds] = useState(60);
  const stop = useRef(false);

  const refresh = useCallback(() => {
    api.get<Summary>('/publications/summary').then(r => setSummary(r.data)).catch(() => {});
    extensionStatus().then(s => { setExt(s); if (s) setIntervalSeconds(s.send_interval_seconds); });
  }, []);
  useEffect(() => { refresh(); const t = setInterval(refresh, 10000); return () => clearInterval(t); }, [refresh]);
  useEffect(() => { localStorage.setItem('autopost_open_chat', openChat ? '1' : '0'); }, [openChat]);
  useEffect(() => setChecked([]), [tab, group, campaign, search]);

  const reloadAll = () => { list.reload(true); refresh(); };
  const run = async (action: () => Promise<unknown>, fallback: string, ok = '') => {
    setError(''); setNotice('');
    try { await action(); if (ok) setNotice(ok); reloadAll(); } catch (e) { setError(apiError(e, fallback)); }
  };
  const action = (p: Publication, kind: 'approve' | 'cancel') => run(() => api.post(`/publications/${p.id}/${kind}`), 'Ação não concluída.');
  const sendOne = async (p: Publication) => {
    setBusy(p.id); setError(''); setNotice('');
    try {
      const result = await sendPublication(p.id, openChat);
      const preview = result.preview ? ` Prévia do link: ${result.preview}.` : '';
      setNotice(result.confirmed === false ? `Enviada para "${result.group}", mas não consegui confirmar a mensagem na conversa. Confira no WhatsApp.${preview}` : `Enviada para "${result.group}".${preview}`);
      return true;
    } catch (e) { setError(apiError(e, 'Falha no envio.')); return false; }
    finally { setBusy(null); reloadAll(); }
  };
  const testOne = async (p: Publication) => {
    setBusy(p.id); setError(''); setNotice('');
    try {
      const r = await testSendInWhatsApp(p.id);
      setNotice(p.send_mode === 'image'
        ? 'Ensaio concluído: a foto abriu no editor do WhatsApp com a legenda completa. Nada foi enviado.'
        : `Ensaio concluído: o texto foi colado no grupo e apagado. Prévia do link: ${r.preview || 'sem link'}. Nada foi enviado.`);
    } catch (e) { setError(apiError(e, 'O ensaio falhou.')); }
    finally { setBusy(null); }
  };
  const runQueue = async () => {
    stop.current = false; setRunning(true); let sent = 0;
    try {
      while (!stop.current) {
        const queue = (await api.get<Publication[]>('/publications/queue', {params: {limit: 1}})).data;
        if (!queue.length) break;
        setProgress(`Enviando para "${queue[0].group_name}"…`);
        if (await sendOne(queue[0])) sent++; else break;
        for (let s = Math.max(interval, ext?.min_interval_seconds ?? 20); s > 0 && !stop.current; s--) { setCountdown(s); await sleep(1000); }
        setCountdown(0);
      }
    } finally { setRunning(false); setProgress(''); setCountdown(0); if (sent) setNotice(`${sent} mensagem(ns) enviada(s) nesta rodada.`); reloadAll(); }
  };
  const toggleAuto = async (enabled: boolean) => {
    try { setExt(await setAutoSend(enabled, interval)); setNotice(enabled ? 'Envio automático ligado: a extensão envia a fila mesmo com o painel fechado.' : 'Envio automático desligado.'); }
    catch (e) { setError(apiError(e, 'Não consegui falar com a extensão.')); }
  };
  const editDraft = (p: Publication): Draft => ({id: p.id, product_id: String(p.product_id), group_name: p.group_name, scheduled: toLocalInput(p.scheduled_at), message: p.message, force_repost: false,
    send_mode: p.send_mode_choice ?? 'default'});
  const selectable = list.items.filter(p => [...EDITABLE, 'paused'].includes(p.status)).map(p => p.id);
  const chosen = list.items.filter(p => checked.includes(p.id));
  const canApprove = chosen.filter(p => ['pending', 'awaiting_approval', 'failed'].includes(p.status) || (p.status === 'scheduled' && !p.approved_at));
  const bulkCancel = async () => {
    if (!await confirm.ask(`Remover ${checked.length} publicação(ões) da fila?`, 'Elas ficam na aba Canceladas e não serão enviadas.', 'Remover da fila')) return;
    run(async () => { const r = await api.post('/publications/bulk/cancel', {ids: checked}); setChecked([]); setNotice(`${r.data.cancelled} publicação(ões) removida(s) da fila.`); }, 'Falha ao remover da fila.');
  };
  const bulkApprove = () => run(async () => { const r = await api.post('/publications/bulk/approve', {ids: canApprove.map(p => p.id)}); setChecked([]);
    setNotice(tab === 'failed' ? `${r.data.length} publicação(ões) liberada(s) para reenviar.` : `${r.data.length} publicação(ões) aprovada(s).`); }, 'Falha ao aprovar em lote.');
  const extReady = Boolean(ext?.whatsapp_tab);

  return <>
    <PageHeader title="Fila" description="Publicações do aprovado ao enviado. A extensão envia pela sua aba do WhatsApp Web."
      actions={<Button variant="contained" onClick={() => setDraft({product_id: '', group_name: '', scheduled: '', message: '', force_repost: false, send_mode: 'default'})}>Nova publicação</Button>}/>
    <Tabs value={tab} onChange={(_, v) => setParams({tab: v})} variant="scrollable" allowScrollButtonsMobile sx={{mb: 2, borderBottom: 1, borderColor: 'divider'}}>
      {TABS.map(([key, label]) => <Tab key={key} value={key} label={<Badge color={key === 'failed' ? 'error' : 'primary'} badgeContent={summary[key] || 0} max={999} sx={{pr: 2.25, '& .MuiBadge-badge': {fontWeight: 700}}}>{label}</Badge>}/>)}
    </Tabs>

    {tab === 'approved' && <Card sx={{mb: 2}}><CardContent>
      {!ext ? <Alert severity="warning">Extensão do Autopost não encontrada. Instale a pasta "extension" no Chrome e aperte F5.</Alert>
        : !ext.logged_in ? <Alert severity="warning">A extensão ainda não recebeu seu login. Aperte F5 nesta página.</Alert>
        : !ext.whatsapp_tab ? <Alert severity="warning">Abra o WhatsApp Web (web.whatsapp.com) em uma aba deste Chrome para enviar.</Alert>
        : <Alert severity="success">Pronto para enviar pela sua aba do WhatsApp Web. Preços lidos há mais de 6 h são conferidos na loja antes de cada envio.</Alert>}
      <Stack direction={{xs: 'column', md: 'row'}} spacing={2} alignItems={{md: 'center'}} mt={2} flexWrap="wrap" useFlexGap>
        <TextField size="small" type="number" label="Intervalo entre envios (s)" value={interval} inputProps={{min: ext?.min_interval_seconds ?? 20}}
          onChange={e => setIntervalSeconds(Math.max(ext?.min_interval_seconds ?? 20, Number(e.target.value) || 60))} sx={{width: 200}}/>
        {running ? <Button color="error" variant="outlined" onClick={() => { stop.current = true; }}>Parar</Button>
          : <Button variant="contained" disabled={!extReady || !list.total || busy !== null} onClick={runQueue}>Enviar fila agora ({summary.approved || 0})</Button>}
        <FormControlLabel control={<Switch checked={Boolean(ext?.auto_send)} disabled={!ext} onChange={e => toggleAuto(e.target.checked)}/>} label="Envio automático (mesmo com o painel fechado)"/>
        <FormControlLabel control={<Checkbox checked={openChat} onChange={e => setOpenChat(e.target.checked)}/>} label="Enviar para a conversa já aberta"/>
      </Stack>
      {(progress || countdown > 0) && <Typography variant="body2" mt={1}>{progress}{countdown > 0 ? ` Próxima em ${countdown} s.` : ''}</Typography>}
      {ext?.auto_send && ext.queue_status && <Typography variant="caption" color="text.secondary" display="block" mt={1}>Envio automático: {ext.queue_status.text} ({timeAgo(new Date(ext.queue_status.at).toISOString())})</Typography>}
      {openChat && <Typography variant="caption" color="text.secondary" display="block" mt={1}>Conversa já aberta: abra o grupo no WhatsApp Web antes de enviar. A extensão confere o nome do grupo e não envia se for outro.</Typography>}
    </CardContent></Card>}

    <Stack direction={{xs: 'column', md: 'row'}} gap={1} mb={2} alignItems={{md: 'center'}} flexWrap="wrap">
      <TextField size="small" placeholder="Buscar produto" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => e.key === 'Enter' && setSearch(query)}
        onBlur={() => setSearch(query)} InputProps={{startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small"/></InputAdornment>}}/>
      <TextField size="small" select label="Grupo" value={group} onChange={e => setParam('group', e.target.value)} sx={{minWidth: 180}}>
        <MenuItem value="">Todos</MenuItem>{groups.map(g => <MenuItem key={g} value={g}>{g}</MenuItem>)}</TextField>
      <TextField size="small" select label="Campanha" value={campaign} onChange={e => setParam('campaign', e.target.value)} sx={{minWidth: 180}}>
        <MenuItem value="">Todas</MenuItem>{campaigns.map(c => <MenuItem key={c.id} value={String(c.id)}>{c.name}</MenuItem>)}</TextField>
      {(group || campaign || search) && <Button onClick={() => { setParam('group', ''); setParam('campaign', ''); setQuery(''); setSearch(''); }}>Limpar filtros</Button>}
      <Box flex={1}/>
      {list.items.length > 1 && <ExpandAll onExpand={() => setExpanded(list.items.map(p => p.id))} onCollapse={() => setExpanded([])}/>}
      <Tooltip title="Atualizar lista"><IconButton aria-label="Atualizar lista" onClick={reloadAll}><RefreshIcon/></IconButton></Tooltip>
    </Stack>
    {selectable.length > 0 && <SelectAll total={selectable.length} selected={checked.length} onAll={() => setChecked(selectable)} onNone={() => setChecked([])}/>}

    <Feedback error={error || list.error} notice={notice} onRetry={list.error ? () => list.reload() : undefined} onClose={() => { setError(''); setNotice(''); list.setError(''); }}/>
    <Loading show={list.loading}/>
    {!list.loading && !list.items.length && <Empty text="Nenhuma publicação nesta aba."/>}

    <Stack spacing={2}>{list.items.map(p => {
      const [label, color] = publicationLabel(p.status);
      return <Card key={p.id}><CardContent sx={{display: 'flex', gap: 3, flexDirection: {xs: 'column', md: 'row'}, p: {md: 2.5}, '&:last-child': {pb: {md: 2.5}}}}>
        {selectable.includes(p.id) &&
          <Checkbox sx={{alignSelf: 'flex-start', m: -1}} checked={checked.includes(p.id)} onChange={() => setChecked(c => c.includes(p.id) ? c.filter(x => x !== p.id) : [...c, p.id])} inputProps={{'aria-label': 'Selecionar publicação'}}/>}
        <Collapse in={expanded.includes(p.id)} unmountOnExit sx={{flexShrink: 0}}><WhatsAppPreview message={p.message}/></Collapse>
        <Box flex={1} minWidth={0}>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
            <Typography fontWeight={650} fontSize={16}>{p.product?.title || `Produto ${p.product_id}`}</Typography><Chip size="small" color={color} label={label}/>
          </Stack>
          {p.product && <Box my={1.25}><PriceTag price={p.product.price} original={p.product.original_price} note={p.product.price_note} size="sm"/></Box>}
          <Typography variant="body2" color={p.group_name ? 'text.primary' : 'error'} fontWeight={600}>{p.group_name ? `Grupo ${p.group_name}` : 'Grupo não definido: edite a publicação'}</Typography>
          <Meta items={[p.scheduled_at && `Agendada para ${new Date(p.scheduled_at).toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'})}`,
            p.status === 'scheduled' && (p.approved_at ? 'Já aprovada' : 'Precisa de aprovação'),
            p.sent_at && `Enviada em ${new Date(p.sent_at).toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'})}`,
            p.send_mode === 'image' && 'Envio: foto + texto',
            p.send_attempts > 0 && `${p.send_attempts} tentativa(s)`, p.product && `Preço lido ${timeAgo(p.product.captured_at)}`,
            p.campaign_id && `Campanha ${campaigns.find(c => c.id === p.campaign_id)?.name ?? `#${p.campaign_id}`}`]}/>
          {p.last_error && <Alert severity="error" sx={{my: 1}}>{p.last_error}</Alert>}
          <Stack direction="row" flexWrap="wrap" gap={1} mt={1}>
            {p.status === 'approved' && <Button variant="contained" size="small" disabled={!extReady || busy !== null || running || !p.group_name} onClick={() => sendOne(p)}>{busy === p.id ? 'Enviando…' : 'Enviar agora'}</Button>}
            {['approved', 'scheduled', 'failed'].includes(p.status) && p.group_name && <Tooltip title="Abre o grupo, cola a mensagem (ou a foto com legenda), confere e apaga. Nada é enviado.">
              <span><Button size="small" disabled={!extReady || busy !== null || running} onClick={() => testOne(p)}>{busy === p.id ? 'Ensaiando…' : 'Ensaiar no WhatsApp'}</Button></span></Tooltip>}
            {['pending', 'awaiting_approval'].includes(p.status) && <Button size="small" variant="contained" onClick={() => action(p, 'approve')}>Aprovar</Button>}
            {p.status === 'failed' && <Button size="small" variant="contained" onClick={() => action(p, 'approve')}>Liberar para reenviar</Button>}
            {p.status === 'scheduled' && !p.approved_at && <Button size="small" onClick={() => action(p, 'approve')}>Aprovar agendamento</Button>}
            {EDITABLE.includes(p.status) && <Button size="small" onClick={() => setDraft(editDraft(p))}>Editar</Button>}
            {EDITABLE.includes(p.status) && <Button size="small" color="error" onClick={() => action(p, 'cancel')}>Cancelar</Button>}
            <Button size="small" onClick={() => setExpanded(e => e.includes(p.id) ? e.filter(x => x !== p.id) : [...e, p.id])} aria-expanded={expanded.includes(p.id)}>
              {expanded.includes(p.id) ? 'Ocultar mensagem' : 'Ver mensagem'}</Button>
            {p.status === 'sent' && <Button size="small" onClick={() => setDraft({product_id: String(p.product_id), group_name: p.group_name, scheduled: '', message: '', force_repost: true, send_mode: p.send_mode_choice ?? 'default'})}>Repostar</Button>}
          </Stack>
        </Box>
      </CardContent></Card>;
    })}</Stack>
    <LoadMore show={list.hasMore} loading={list.loading} onClick={list.loadMore}/>
    <BulkBar count={checked.length} noun="publicação(ões) selecionada(s)" onClear={() => setChecked([])}>
      {canApprove.length > 0 && <Button size="small" variant="outlined" onClick={bulkApprove}>{tab === 'failed' ? `Reenviar (${canApprove.length})` : `Aprovar (${canApprove.length})`}</Button>}
      <Button size="small" variant="outlined" onClick={bulkCancel}>Remover da fila</Button>
    </BulkBar>
    {confirm.dialog}
    <PublicationDialog draft={draft} onClose={() => setDraft(null)} onError={setError}
      onSaved={text => { setDraft(null); setNotice(text); reloadAll(); }}/>
  </>;
}
