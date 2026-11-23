import {useEffect, useState, type ReactNode} from 'react';
import {Link, useSearchParams} from 'react-router-dom';
import {Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, MenuItem, Radio, RadioGroup, Stack, Tab, Tabs, TextField, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {Listing, Search} from '../types/search';
import {timeAgo} from '../labels';
import {usePaged} from '../hooks/usePaged';
import {Empty, Feedback, Loading, LoadMore} from '../components/Feedback';
import {Meta, PageHeader, PriceTag} from '../components/Ui';
import {BulkBar, SelectAll, SelectMatching, fetchAllIds, inBatches, useConfirm} from '../components/Bulk';
import {DeleteIcon} from '../components/Icons';

const TABS: [string, string][] = [['new', 'Para aprovar'], ['scheduled', 'Agendados'], ['discarded', 'Descartados'], ['rejected', 'Fora dos filtros']];
type Result = {scheduled: {id: number; scheduled_at: string}[]; skipped: {id: number; reason: string}[]};

const when = (iso: string) => new Date(iso).toLocaleString('pt-BR', {weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit'});
function summary(result: Result): string {
  if (!result.scheduled.length && !result.skipped.length) return 'Nada para agendar.';
  const times = result.scheduled.map(s => s.scheduled_at).sort();
  const parts: string[] = [];
  if (times.length) parts.push(`${times.length} agendado(s): de ${when(times[0])} até ${when(times[times.length - 1])}`);
  if (result.skipped.length) parts.push(`${result.skipped.length} ignorado(s) (${[...new Set(result.skipped.map(s => s.reason))].join('; ')})`);
  return parts.join('. ') + '.';
}

function ScheduleDialog({ids, onClose, onDone, onError}: {ids: number[] | null; onClose: () => void; onDone: (text: string) => void; onError: (t: string) => void}) {
  const [mode, setMode] = useState<'auto' | 'time'>('auto'), [time, setTime] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { setMode('auto'); setTime(''); }, [ids]);
  if (!ids) return null;
  const tooMany = ids.length > 200;
  const submit = async () => {
    setBusy(true);
    try {
      if (mode === 'time') {
        onDone(summary((await api.post<Result>('/listings/approve', {ids, scheduled_at: new Date(time).toISOString()})).data));
      } else {   // em lotes de 200: cada lote continua a agenda de onde o anterior parou
        const all: Result = {scheduled: [], skipped: []};
        for (let i = 0; i < ids.length; i += 200) {
          const r = (await api.post<Result>('/listings/approve', {ids: ids.slice(i, i + 200), scheduled_at: null})).data;
          all.scheduled.push(...r.scheduled); all.skipped.push(...r.skipped);
        }
        onDone(summary(all));
      }
    } catch (e) { onError(apiError(e, 'Não foi possível agendar.')); }
    finally { setBusy(false); }
  };
  return <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
    <DialogTitle>Aprovar {ids.length} achado(s)</DialogTitle>
    <DialogContent>
      <RadioGroup value={mode} onChange={e => setMode(e.target.value as 'auto' | 'time')}>
        <FormControlLabel value="auto" control={<Radio/>} label="Distribuir nos próximos horários livres do grupo"/>
        <FormControlLabel value="time" control={<Radio/>} disabled={tooMany} label={tooMany ? 'Escolher o horário (até 200 por vez)' : 'Escolher o horário'}/>
      </RadioGroup>
      {mode === 'time' && <TextField fullWidth sx={{mt: 1}} type="datetime-local" label="Primeiro envio" InputLabelProps={{shrink: true}}
        helperText="Se forem vários, os seguintes saem com o intervalo da agenda do grupo." value={time} onChange={e => setTime(e.target.value)}/>}
      <Typography variant="body2" color="text.secondary" mt={2}>O link de afiliado é gerado pela extensão (botão Compartilhar do Mercado Livre)
        logo antes de cada envio, junto com a conferência do preço.</Typography>
    </DialogContent>
    <DialogActions><Button onClick={onClose}>Cancelar</Button>
      <Button variant="contained" disabled={busy || (mode === 'time' && !time)} onClick={submit}>Aprovar</Button></DialogActions>
  </Dialog>;
}

function ListingCard({item, selected, onToggle, actions}: {item: Listing; selected: boolean; onToggle?: () => void; actions?: ReactNode}) {
  const lowest = item.min_price_30d != null && item.price != null && item.price <= item.min_price_30d;
  return <Card variant="outlined" sx={{borderColor: selected ? 'primary.main' : undefined}}>
    <CardContent sx={{display: 'flex', flexWrap: {xs: 'wrap', sm: 'nowrap'}, gap: 2, alignItems: 'flex-start', p: {xs: 1.5, sm: 2.5}, '&:last-child': {pb: {xs: 1.5, sm: 2.5}}}}>
      {onToggle && <Checkbox checked={selected} onChange={onToggle} sx={{mt: -1, ml: -1}} inputProps={{'aria-label': 'Selecionar'}}/>}
      <Box component="img" src={item.image_url} alt="" loading="lazy" referrerPolicy="no-referrer"
        sx={{width: {xs: 72, sm: 104}, height: {xs: 72, sm: 104}, objectFit: 'contain', borderRadius: 2, bgcolor: '#fff', flexShrink: 0, border: '1px solid', borderColor: 'divider'}}/>
      <Box flex={1} minWidth={{xs: 'calc(100% - 140px)', sm: 0}}>
        <Typography fontWeight={650} fontSize={15.5} sx={{display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>
          <a href={item.url} target="_blank" rel="noreferrer" style={{color: 'inherit'}}>{item.title}</a></Typography>
        <Box my={1}><PriceTag price={item.price} original={item.original_price} note={item.price_note}/></Box>
        <Stack direction="row" spacing={.75} flexWrap="wrap" useFlexGap mt={1}>
          <Chip size="small" color={item.score >= 70 ? 'primary' : 'default'} variant={item.score >= 70 ? 'filled' : 'outlined'} label={`Nota ${item.score}`}/>
          {lowest && <Chip size="small" color="success" label="Menor preço em 30 dias"/>}
          {item.rating != null && <Chip size="small" variant="outlined" label={`★ ${item.rating}`}/>}
          {item.sold != null && <Chip size="small" variant="outlined" label={`${item.sold.toLocaleString('pt-BR')}+ vendidos`}/>}
          {item.free_shipping && <Chip size="small" variant="outlined" label="Frete grátis"/>}
          {item.reject_reason && <Chip size="small" color="warning" label={item.reject_reason}/>}
        </Stack>
        <Box mt={1}><Meta items={[item.seller && `Vendido por ${item.seller}`, `Busca "${item.term}"`, `Visto ${timeAgo(item.last_seen_at)}`]}/></Box>
      </Box>
      {actions && <Stack direction={{xs: 'row', sm: 'column'}} gap={1} flexShrink={0} sx={{width: {xs: '100%', sm: 'auto'}, justifyContent: 'flex-end'}}>{actions}</Stack>}
    </CardContent>
  </Card>;
}

export default function ListingsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') || 'new', searchId = params.get('search') || '';
  const [searches, setSearches] = useState<Search[]>([]);
  const [selected, setSelected] = useState<number[]>([]), [dialog, setDialog] = useState<number[] | null>(null);
  const [notice, setNotice] = useState(''), [busy, setBusy] = useState(false);
  const query = tab === 'rejected' ? {status: 'new', matches: 'false'} : {status: tab, matches: tab === 'new' ? 'true' : 'all'};
  const listParams = {...query, search_id: searchId || undefined};
  const {items, total, loading, error, setError, reload, loadMore, hasMore} = usePaged<Listing>('/listings', listParams, 40);
  const confirm = useConfirm();
  const selectable = tab === 'scheduled' ? [] : items.map(i => i.id);   // agendados já viraram publicação: as ações ficam na Fila
  const pageSelected = selectable.length > 0 && selectable.every(id => selected.includes(id));
  useEffect(() => { api.get<Search[]>('/searches').then(r => setSearches(r.data)).catch(() => {}); }, []);
  useEffect(() => setSelected([]), [tab, searchId]);
  const set = (key: string, value: string) => { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); setParams(next); };
  const toggle = (id: number) => setSelected(old => old.includes(id) ? old.filter(x => x !== id) : [...old, id]);
  const done = (text: string) => { setDialog(null); setSelected([]); setNotice(text); reload(); };
  const discard = async (ids: number[]) => {
    try { const r = await inBatches(ids, chunk => api.post('/listings/discard', {ids: chunk})); setSelected([]); setNotice(`${r.discarded ?? 0} descartado(s).`); reload(); }
    catch (e) { setError(apiError(e, 'Não foi possível descartar.')); }
  };
  const restore = async (ids: number[]) => {
    try { const r = await inBatches(ids, chunk => api.post('/listings/restore', {ids: chunk})); setSelected([]); setNotice(`${r.restored ?? 0} achado(s) de volta em "Para aprovar".`); reload(); }
    catch (e) { setError(apiError(e, 'Não foi possível restaurar.')); }
  };
  const acceptAll = async () => {
    if (!await confirm.ask(`Aprovar todos os ${total} achados?`, `Os achados${searchId ? ' desta busca' : ''} (até 200 de cada vez, os de maior nota primeiro) são distribuídos nos horários livres dos grupos.`, 'Aprovar todos')) return;
    setBusy(true);
    try { done(summary((await api.post<Result>('/listings/accept-all', {search_id: searchId ? Number(searchId) : null})).data)); }
    catch (e) { setError(apiError(e, 'Não foi possível aprovar.')); }
    finally { setBusy(false); }
  };

  return <Box>
    <PageHeader title="Achados" description={<>Ofertas encontradas pelas <Link to="/searches">buscas automáticas</Link>, da melhor nota para a pior.</>}
      actions={<TextField select size="small" label="Busca" value={searchId} onChange={e => set('search', e.target.value)} sx={{minWidth: 220}}
        SelectProps={{displayEmpty: true}} InputLabelProps={{shrink: true}}>
        <MenuItem value="">Todas</MenuItem>{searches.map(s => <MenuItem key={s.id} value={String(s.id)}>{s.name}</MenuItem>)}
      </TextField>}/>
    <Tabs value={tab} onChange={(_, v) => set('tab', v === 'new' ? '' : v)} variant="scrollable" sx={{my: 2, borderBottom: 1, borderColor: 'divider'}}>
      {TABS.map(([v, l]) => <Tab key={v} value={v} label={v === tab ? `${l} (${total})` : l}/>)}
    </Tabs>
    <Feedback error={error} notice={notice} onRetry={() => reload()} onClose={() => { setError(''); setNotice(''); }}/>
    {selectable.length > 0 && <Stack direction="row" spacing={1} mb={1} flexWrap="wrap" useFlexGap alignItems="center">
      <SelectAll total={selectable.length} selected={selectable.filter(id => selected.includes(id)).length}
        onAll={() => setSelected(old => [...new Set([...old, ...selectable])])} onNone={() => setSelected([])} label={`Selecionar os ${selectable.length} desta página`}/>
      <Box flex={1}/>
      {tab === 'new' && <Button variant="outlined" disabled={busy} onClick={acceptAll}>Aceitar todos ({total})</Button>}
    </Stack>}
    <SelectMatching pageCount={selectable.length} pageSelected={pageSelected} selected={selected.length} total={total} noun="achados"
      onSelectAll={async () => setSelected(await fetchAllIds('/listings', listParams))} onClear={() => setSelected([])}/>
    <Loading show={loading}/>
    {!loading && !items.length && <Empty text={tab === 'new' ? 'Nenhum achado esperando aprovação. As buscas trazem novos itens conforme a frequência de cada uma.' : 'Nada aqui.'}/>}
    <Stack spacing={1.5}>
      {items.map(item => <ListingCard key={item.id} item={item} selected={selected.includes(item.id)}
        onToggle={selectable.length ? () => toggle(item.id) : undefined}
        actions={tab === 'new' ? <>
          <Button size="small" variant="contained" onClick={() => setDialog([item.id])}>Aprovar</Button>
          <Button size="small" color="error" onClick={() => discard([item.id])}>Descartar</Button>
        </> : tab === 'rejected' ? <Button size="small" color="error" onClick={() => discard([item.id])}>Descartar</Button>
          : tab === 'discarded' ? <Button size="small" onClick={() => restore([item.id])}>Restaurar</Button>
          : tab === 'scheduled' && item.publication_id ? <Button size="small" component={Link} to="/queue?tab=scheduled">Ver na fila</Button> : undefined}/>)}
    </Stack>
    <LoadMore show={hasMore} onClick={loadMore} loading={loading}/>
    <ScheduleDialog ids={dialog} onClose={() => setDialog(null)} onDone={done} onError={setError}/>
    <BulkBar count={selected.length} noun="achado(s) selecionado(s)" onClear={() => setSelected([])}>
      {tab === 'new' && <Button size="small" variant="outlined" onClick={() => setDialog(selected)}>Aprovar</Button>}
      {(tab === 'new' || tab === 'rejected') && <Button size="small" variant="outlined" startIcon={<DeleteIcon/>} onClick={() => discard(selected)}>Descartar</Button>}
      {tab === 'discarded' && <Button size="small" variant="outlined" onClick={() => restore(selected)}>Restaurar para aprovação</Button>}
    </BulkBar>
    {confirm.dialog}
  </Box>;
}
