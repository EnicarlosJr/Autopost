import {useCallback, useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {Alert, Box, Button, Card, CardContent, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, FormControlLabel, Grid, MenuItem, Stack, Switch, TextField, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {extensionStatus, runSearches} from '../services/sender';
import type {Search} from '../types/search';
import {timeAgo} from '../labels';
import {Empty, Feedback, Loading} from '../components/Feedback';
import {Meta, PageHeader} from '../components/Ui';
import {BulkBar, SelectAll, eachItem, useConfirm, useSelection} from '../components/Bulk';
import {GroupPicker} from '../components/Fields';
import {DeleteIcon} from '../components/Icons';

type Draft = Omit<Search, 'id' | 'last_run_at' | 'next_run_at' | 'last_result' | 'pending'> & {id?: number};
const EMPTY: Draft = {name: '', terms: '', exclude_terms: 'usado\nrecondicionado\nréplica', min_price: null, max_price: null, min_discount: 20,
  min_rating: 4, free_shipping_only: false, group_name: '', mode: 'approval', interval_minutes: 120, max_per_run: 5, active: true};
const INTERVALS: [number, string][] = [[30, 'a cada 30 min'], [60, 'a cada 1 hora'], [120, 'a cada 2 horas'], [240, 'a cada 4 horas'],
  [480, 'a cada 8 horas'], [720, 'a cada 12 horas'], [1440, 'uma vez por dia']];
const num = (value: string) => value.trim() === '' ? null : Number(value.replace(',', '.'));
const when = (iso: string | null) => iso ? new Date(iso).toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'}) : '';

function SearchDialog({draft, onClose, onSaved, onError}: {draft: Draft | null; onClose: () => void;
  onSaved: (text: string) => void; onError: (text: string) => void}) {
  const [value, setValue] = useState<Draft | null>(draft), [busy, setBusy] = useState(false);
  useEffect(() => setValue(draft), [draft]);
  if (!value) return null;
  const set = (patch: Partial<Draft>) => setValue({...value, ...patch});
  const save = async () => {
    setBusy(true);
    try {
      const {id, ...body} = value;
      if (id) await api.put(`/searches/${id}`, body); else await api.post('/searches', body);
      onSaved(id ? 'Busca atualizada.' : 'Busca criada. A extensão roda a primeira leitura em até 30 segundos.');
    } catch (e) { onError(apiError(e, 'Não foi possível salvar a busca.')); }
    finally { setBusy(false); }
  };
  return <Dialog open onClose={onClose} maxWidth="md" fullWidth>
    <DialogTitle>{value.id ? 'Editar busca' : 'Nova busca'}</DialogTitle>
    <DialogContent><Grid container spacing={2} sx={{pt: 1}}>
      <Grid item xs={12} md={6}><TextField fullWidth label="Nome (nicho)" placeholder="Ferramentas" value={value.name} onChange={e => set({name: e.target.value})}/></Grid>
      <Grid item xs={12} md={6}><GroupPicker value={value.group_name} onChange={v => set({group_name: v})} label="Grupo de destino"/></Grid>
      <Grid item xs={12} md={6}><TextField fullWidth multiline minRows={4} label="Termos de busca (um por linha, até 10)"
        placeholder={'lanterna tática\nparafusadeira\nkit chaves'} value={value.terms} onChange={e => set({terms: e.target.value})}
/>
        <Stack direction="row" alignItems="center" gap={1} mt={.5}>
          <Button size="small" disabled={/^ofertas do dia$/im.test(value.terms)}
            onClick={() => set({terms: [value.terms.trim(), 'ofertas do dia'].filter(Boolean).join('\n')})}>+ Ofertas do dia do ML</Button>
          <Typography variant="caption" color="text.secondary">Lê 3 páginas de ofertas. Também aceita um link do Mercado Livre por linha.</Typography>
        </Stack></Grid>
      <Grid item xs={12} md={6}><TextField fullWidth multiline minRows={4} label="Palavras proibidas no título (uma por linha)"
        value={value.exclude_terms} onChange={e => set({exclude_terms: e.target.value})}/></Grid>
      <Grid item xs={6} md={3}><TextField fullWidth label="Preço mínimo (R$)" value={value.min_price ?? ''} onChange={e => set({min_price: num(e.target.value)})}/></Grid>
      <Grid item xs={6} md={3}><TextField fullWidth label="Preço máximo (R$)" value={value.max_price ?? ''} onChange={e => set({max_price: num(e.target.value)})}/></Grid>
      <Grid item xs={6} md={3}><TextField fullWidth type="number" label="Desconto mínimo (%)" value={value.min_discount}
        onChange={e => set({min_discount: Math.max(0, Number(e.target.value) || 0)})}/></Grid>
      <Grid item xs={6} md={3}><TextField fullWidth label="Nota mínima (0 a 5)" value={value.min_rating ?? ''} onChange={e => set({min_rating: num(e.target.value)})}/></Grid>
      <Grid item xs={12} md={4}><TextField select fullWidth label="Frequência da busca" value={value.interval_minutes}
        onChange={e => set({interval_minutes: Number(e.target.value)})}>{INTERVALS.map(([v, l]) => <MenuItem key={v} value={v}>{l}</MenuItem>)}</TextField></Grid>
      <Grid item xs={12} md={4}><TextField select fullWidth label="O que fazer com os achados" value={value.mode}
        onChange={e => set({mode: e.target.value as Draft['mode']})}>
        <MenuItem value="approval">Eu aprovo na tela Achados</MenuItem>
        <MenuItem value="auto">Agendar automaticamente os melhores</MenuItem></TextField></Grid>
      <Grid item xs={12} md={4}><TextField fullWidth type="number" disabled={value.mode !== 'auto'} label="Máximo agendado por busca"
        value={value.max_per_run} onChange={e => set({max_per_run: Math.max(1, Number(e.target.value) || 1)})}/></Grid>
      <Grid item xs={12}><Stack direction="row" spacing={3} flexWrap="wrap">
        <FormControlLabel control={<Switch checked={value.free_shipping_only} onChange={e => set({free_shipping_only: e.target.checked})}/>} label="Só com frete grátis"/>
        <FormControlLabel control={<Switch checked={value.active} onChange={e => set({active: e.target.checked})}/>} label="Busca ativa"/>
      </Stack></Grid>
      {value.mode === 'auto' && <Grid item xs={12}><Alert severity="info">No modo automático, a cada busca os anúncios com melhor nota são
        agendados nos horários livres do grupo, sem passar pela sua aprovação.</Alert></Grid>}
    </Grid></DialogContent>
    <DialogActions><Button onClick={onClose}>Cancelar</Button>
      <Button variant="contained" disabled={busy || !value.name.trim() || !value.terms.trim()} onClick={save}>Salvar</Button></DialogActions>
  </Dialog>;
}

export default function SearchesPage() {
  const [searches, setSearches] = useState<Search[]>([]);
  const sel = useSelection(); const confirm = useConfirm();
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null), [running, setRunning] = useState(false), [extension, setExtension] = useState<boolean | null>(null);
  const load = useCallback(async () => {
    try {
      setSearches((await api.get<Search[]>('/searches')).data); setError('');
    } catch (e) { setError(apiError(e, 'Não foi possível carregar as buscas.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); extensionStatus().then(s => setExtension(Boolean(s))); const t = setInterval(load, 20000); return () => clearInterval(t); }, [load]);
  const saved = (text: string) => { setDraft(null); setNotice(text); load(); };
  const runNow = async (search: Search) => {
    setRunning(true); setNotice(''); setError('');
    try {
      await api.post(`/searches/${search.id}/run`);
      const result = await runSearches();
      setNotice(result?.message ? `"${search.name}": ${result.message}` : 'Busca pedida. A extensão roda em até 30 segundos.');
    } catch (e) { setError(apiError(e, 'Não foi possível rodar a busca.')); }
    finally { setRunning(false); load(); }
  };
  const setActive = (search: Search, active: boolean) => {
    const {id, last_run_at, next_run_at, last_result, pending, ...body} = search; // eslint-disable-line @typescript-eslint/no-unused-vars
    return api.put(`/searches/${id}`, {...body, active});
  };
  const toggle = async (search: Search) => {
    try { await setActive(search, !search.active); load(); }
    catch (e) { setError(apiError(e, 'Não foi possível alterar a busca.')); }
  };
  const remove = async (search: Search) => {
    if (!await confirm.ask(`Excluir a busca "${search.name}"?`, 'Os achados já encontrados continuam na tela Achados.', 'Excluir')) return;
    try { await api.delete(`/searches/${search.id}`); setNotice('Busca excluída.'); load(); }
    catch (e) { setError(apiError(e, 'Não foi possível excluir a busca.')); }
  };
  const chosen = searches.filter(s => sel.has(s.id));
  const bulk = async (kind: 'on' | 'off' | 'delete') => {
    if (kind === 'delete' && !await confirm.ask(`Excluir ${chosen.length} busca(s)?`, 'Os achados já encontrados continuam na tela Achados.', 'Excluir')) return;
    setError(''); setNotice('');
    const r = await eachItem(chosen, s => kind === 'delete' ? api.delete(`/searches/${s.id}`) : setActive(s, kind === 'on'));
    setNotice(`${r.ok} busca(s) ${kind === 'delete' ? 'excluída(s)' : kind === 'on' ? 'ativada(s)' : 'pausada(s)'}.${r.failed ? ` ${r.failed} falharam.` : ''}`);
    sel.clear(); load();
  };

  return <Box>
    <PageHeader title="Buscas" description={<>A extensão procura ofertas no Mercado Livre pelo seu Chrome e guarda o que encontrar em <Link to="/listings">Achados</Link>.</>}
      actions={<Button variant="contained" onClick={() => setDraft({...EMPTY})}>Nova busca</Button>}/>
    {extension === false && <Alert severity="warning" sx={{my: 2}}>A extensão do Autopost não respondeu. As buscas só rodam com o Chrome aberto,
      a extensão instalada e este painel logado nele.</Alert>}
    <Feedback error={error} notice={notice} onRetry={load} onClose={() => { setError(''); setNotice(''); }}/>
    <Loading show={loading}/>
    {!loading && !searches.length && <Empty text="Nenhuma busca ainda. Crie uma com os termos do seu nicho."/>}
    {searches.length > 0 && <Box mt={2}><SelectAll total={searches.length} selected={sel.count} onAll={() => sel.setAll(searches.map(s => s.id))} onNone={sel.clear}/></Box>}
    <Stack spacing={2} mt={1}>
      {searches.map(s => <Card key={s.id} variant="outlined" sx={{opacity: s.active ? 1 : .6, borderColor: sel.has(s.id) ? 'primary.main' : undefined}}><CardContent>
        <Stack direction={{xs: 'column', md: 'row'}} justifyContent="space-between" spacing={2}>
          <Checkbox checked={sel.has(s.id)} onChange={() => sel.toggle(s.id)} sx={{alignSelf: 'flex-start', m: -1}} inputProps={{'aria-label': `Selecionar ${s.name}`}}/>
          <Box flex={1} minWidth={0}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="h6" fontWeight={700}>{s.name}</Typography>
              <Chip size="small" label={s.mode === 'auto' ? 'Automático' : 'Com aprovação'} color={s.mode === 'auto' ? 'secondary' : 'default'}/>
              {!s.active && <Chip size="small" label="Pausada"/>}
              {s.pending > 0 && <Chip size="small" color="primary" component={Link} to={`/listings?search=${s.id}`} clickable label={`${s.pending} para aprovar`}/>}
            </Stack>
            <Stack direction="row" gap={.75} flexWrap="wrap" mt={1.25} mb={1}>
              {s.terms.split('\n').map(t => <Chip key={t} size="small" variant="outlined" label={t}/>)}
            </Stack>
            <Meta items={[s.group_name ? `Grupo ${s.group_name}` : 'Sem grupo de destino',
              INTERVALS.find(([v]) => v === s.interval_minutes)?.[1] ?? `A cada ${s.interval_minutes} min`,
              s.min_discount > 0 && `Desconto a partir de ${s.min_discount}%`, s.min_rating && `Nota a partir de ${s.min_rating}`,
              (s.min_price != null || s.max_price != null) && `De R$ ${s.min_price ?? 0} a ${s.max_price != null ? `R$ ${s.max_price}` : 'sem limite'}`,
              s.free_shipping_only && 'Só frete grátis']}/>
            <Typography variant="body2" color="text.secondary" mt={.75}>
              Última busca {timeAgo(s.last_run_at)}{s.last_result ? `: ${s.last_result}` : ''}.
              {s.active && s.next_run_at ? ` Próxima em ${when(s.next_run_at)}.` : ''}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="flex-start" flexWrap="wrap" useFlexGap>
            <Button size="small" variant="outlined" disabled={running || !s.active} onClick={() => runNow(s)}>{running ? 'Buscando…' : 'Buscar agora'}</Button>
            <Button size="small" onClick={() => setDraft({...s})}>Editar</Button>
            <Button size="small" onClick={() => toggle(s)}>{s.active ? 'Pausar' : 'Ativar'}</Button>
            <Button size="small" color="error" onClick={() => remove(s)}>Excluir</Button>
          </Stack>
        </Stack>
      </CardContent></Card>)}
    </Stack>

    <Typography variant="body2" color="text.secondary" mt={4}>Horários, limites e categorias de cada grupo ficam em <Link to="/groups">Grupos</Link>.
      Para escolher quais produtos vão para quais grupos e em que ritmo, use <Link to="/campaigns">Campanhas</Link>.</Typography>
    <SearchDialog draft={draft} onClose={() => setDraft(null)} onSaved={saved} onError={setError}/>
    <BulkBar count={sel.count} noun="busca(s) selecionada(s)" onClear={sel.clear}>
      <Button size="small" variant="outlined" onClick={() => bulk('on')}>Ativar</Button>
      <Button size="small" variant="outlined" onClick={() => bulk('off')}>Pausar</Button>
      <Button size="small" variant="outlined" startIcon={<DeleteIcon/>} onClick={() => bulk('delete')}>Excluir</Button>
    </BulkBar>
    {confirm.dialog}
  </Box>;
}
