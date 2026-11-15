import {useCallback, useEffect, useState} from 'react';
import {Link, useNavigate} from 'react-router-dom';
import {Box, Button, Card, Chip, Collapse, IconButton, LinearProgress, Stack, Tab, Tabs, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {Campaign} from '../types/campaign';
import type {Publication} from '../types/models';
import {campaignStatus, dateTime, rhythm, strategyLabel, WEEKDAYS} from '../campaignLabels';
import {publicationLabel} from '../labels';
import {Empty, Feedback, Loading} from '../components/Feedback';
import {PageHeader, Meta} from '../components/Ui';
import {ExpandAll, useConfirm} from '../components/Bulk';
import {AddIcon, CopyIcon, DeleteIcon, EditIcon, ExpandIcon, PauseIcon, PlayIcon, RefreshIcon, SearchIcon, StopIcon} from '../components/Icons';
import {display, tokens} from '../theme';

const FILTERS: [string, string, string[]][] = [
  ['active', 'Em andamento', ['scheduled', 'running']], ['paused', 'Pausadas', ['paused']], ['draft', 'Rascunhos', ['draft']],
  ['done', 'Encerradas', ['completed', 'completed_with_failures', 'failed', 'cancelled']], ['all', 'Todas', []],
];

function History({campaign}: {campaign: Campaign}) {
  const [rows, setRows] = useState<Publication[] | null>(null);
  useEffect(() => {
    api.get<Publication[]>('/publications', {params: {campaign_id: campaign.id, limit: 200, sort: 'oldest'}}).then(r => setRows(r.data)).catch(() => setRows([]));
  }, [campaign.id, campaign.sent, campaign.pending]);
  if (!rows) return <LinearProgress/>;
  if (!rows.length) return <Typography color="text.secondary" fontSize={14}>Nenhuma publicação gerada ainda. Agende a campanha para criar a fila.</Typography>;
  const ordered = [...rows].sort((a, b) => (a.sent_at || a.scheduled_at || '').localeCompare(b.sent_at || b.scheduled_at || ''));
  return <Box component="ol" sx={{listStyle: 'none', m: 0, p: 0, maxHeight: 320, overflow: 'auto', border: `1px solid ${tokens.line}`, borderRadius: 2}}>
    {ordered.map(p => { const [label, color] = publicationLabel(p.status);
      return <Box component="li" key={p.id} sx={{display: 'grid', gridTemplateColumns: {xs: '1fr auto', sm: '110px 1fr 160px auto'}, gap: 1.5, alignItems: 'center',
        px: 1.5, py: 1, borderBottom: `1px solid ${tokens.line}`, '&:last-child': {borderBottom: 0}, fontSize: 14}}>
        <Typography fontSize={13} color="text.secondary" sx={{display: {xs: 'none', sm: 'block'}}}>{dateTime(p.sent_at || p.scheduled_at)}</Typography>
        <Typography fontSize={14} noWrap title={p.product?.title}>{p.product?.title || `Produto ${p.product_id}`}</Typography>
        <Typography fontSize={13} color="text.secondary" noWrap sx={{display: {xs: 'none', sm: 'block'}}}>{p.group_name}</Typography>
        <Chip size="small" color={color} label={label} title={p.last_error || undefined}/>
      </Box>; })}
  </Box>;
}

function Details({c}: {c: Campaign}) {
  const seg = [c.products_count ? `${c.products_count} produto(s) na campanha` : '',
    c.niche_names?.length ? `Nichos: ${c.niche_names.join(', ')}` : '',
    c.ml_categories?.length ? `Categorias oficiais: ${c.ml_categories.map(x => x.name || x.id).join(', ')}` : '',
    !c.products_count && c.product_ids.length ? `${c.product_ids.length} produtos escolhidos à mão` : '',
    !c.products_count && c.categories.length ? `Categorias: ${c.categories.join(', ')}` : '', c.exclude_categories.length ? `Sem: ${c.exclude_categories.join(', ')}` : '',
    !c.products_count && c.tags.length ? `Tags (${c.tag_mode === 'all' ? 'todas' : 'qualquer uma'}): ${c.tags.join(', ')}` : '',
    c.exclude_tags.length ? `Sem as tags: ${c.exclude_tags.join(', ')}` : '', c.include_uncategorized ? 'Inclui produtos sem categoria' : '',
    c.min_discount ? `Desconto a partir de ${c.min_discount}%` : ''].filter(Boolean);
  const days = c.weekdays.length === 7 ? 'todos os dias' : c.weekdays.map(d => WEEKDAYS[d]).join(', ');
  return <Box sx={{display: 'grid', gap: 2.5, gridTemplateColumns: {xs: '1fr', md: '1fr 1fr'}}}>
    <Box>
      <Typography fontWeight={650} mb={.75}>Configuração</Typography>
      <Stack gap={.5} fontSize={14}>
        <span>Produtos: {seg.length ? seg.join('. ') : 'todos os produtos prontos'}.</span>
        <span>Distribuição: {strategyLabel[c.strategy]?.[0]}, até {c.total_limit} anúncios.</span>
        <span>Ritmo: {rhythm(c)}, das {c.start_hour}h às {c.end_hour}h, {days}.</span>
        {c.end_at && <span>Termina em {dateTime(c.end_at)}.</span>}
        {c.daily_limit > 0 && <span>Limite de {c.daily_limit} por dia.</span>}
        {c.group_daily_limit > 0 && <span>Até {c.group_daily_limit} por grupo por dia.</span>}
        {c.reuse_days != null && <span>Reutiliza um produto no mesmo grupo após {c.reuse_days} dia(s).</span>}
        {c.pause_every > 0 && <span>Pausa de {c.pause_minutes} min a cada {c.pause_every} anúncios.</span>}
        <span>Grupos: {c.groups.map(g => g.limit ? `${g.group} (até ${g.limit})` : g.group).join(', ') || 'nenhum'}.</span>
      </Stack>
    </Box>
    <Box>
      <Typography fontWeight={650} mb={.75}>Histórico de publicações</Typography>
      <History campaign={c}/>
    </Box>
  </Box>;
}

export default function CampaignsPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Campaign[]>([]), [loading, setLoading] = useState(true);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [busy, setBusy] = useState<number | null>(null);
  const [filter, setFilter] = useState('active'), [open, setOpen] = useState<number[]>([]);
  const confirm = useConfirm();
  const load = useCallback(async () => {
    try { setItems((await api.get<Campaign[]>('/campaigns')).data); setError(''); }
    catch (e) { setError(apiError(e, 'Não foi possível carregar as campanhas.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 20000); return () => clearInterval(t); }, [load]);
  const statuses = FILTERS.find(([k]) => k === filter)![2];
  const shown = statuses.length ? items.filter(c => statuses.includes(c.display_status)) : items;
  const act = async (c: Campaign, action: string, ok: string) => {
    setBusy(c.id); setError(''); setNotice('');
    try {
      if (action === 'delete') await api.delete(`/campaigns/${c.id}`);
      else if (action === 'duplicate') { const r = await api.post<Campaign>(`/campaigns/${c.id}/duplicate`); navigate(`/campaigns/${r.data.id}/edit`); return; }
      else await api.post(`/campaigns/${c.id}/${action}`);
      setNotice(ok); await load();
    } catch (e) { setError(apiError(e, 'Ação não concluída.')); }
    finally { setBusy(null); }
  };
  const toggle = (id: number) => setOpen(o => o.includes(id) ? o.filter(x => x !== id) : [...o, id]);

  return <>
    <PageHeader title="Campanhas" description="Defina quais produtos vão para quais grupos, em que ritmo e em quais horários."
      actions={<><Tooltip title="Atualizar lista"><IconButton aria-label="Atualizar lista" onClick={load}><RefreshIcon/></IconButton></Tooltip>
        <Button variant="contained" startIcon={<AddIcon/>} component={Link} to="/campaigns/new">Nova campanha</Button></>}/>
    <Stack direction={{xs: 'column', md: 'row'}} justifyContent="space-between" alignItems={{md: 'center'}} gap={1} sx={{borderBottom: 1, borderColor: 'divider', mb: 2}}>
      <Tabs value={filter} onChange={(_, v) => setFilter(v)} variant="scrollable">
        {FILTERS.map(([k, label, st]) => { const n = st.length ? items.filter(c => st.includes(c.display_status)).length : items.length;
          return <Tab key={k} value={k} label={`${label}${n ? ` (${n})` : ''}`}/>; })}
      </Tabs>
      {shown.length > 1 && <ExpandAll onExpand={() => setOpen(shown.map(c => c.id))} onCollapse={() => setOpen([])}/>}
    </Stack>
    <Feedback error={error} notice={notice} onRetry={load} onClose={() => { setError(''); setNotice(''); }}/>
    <Loading show={loading}/>
    {!loading && !shown.length && <Empty text={items.length ? 'Nenhuma campanha neste filtro.' : 'Nenhuma campanha ainda. Crie a primeira escolhendo produtos, grupos e o ritmo dos envios.'}/>}
    <Stack gap={1.5}>
      {shown.map(c => {
        const [label, color] = campaignStatus[c.display_status] ?? [c.display_status, 'default'];
        const expanded = open.includes(c.id);
        const can = {pause: c.status === 'scheduled', resume: c.status === 'paused', edit: ['draft', 'paused'].includes(c.status),
          schedule: c.status === 'draft', cancel: !['draft', 'cancelled'].includes(c.status) && !['completed', 'completed_with_failures', 'failed'].includes(c.display_status),
          remove: ['draft', 'cancelled', 'completed', 'completed_with_failures', 'failed'].includes(c.display_status)};
        return <Card key={c.id}>
          <Box sx={{display: 'flex', alignItems: 'center', gap: 2, p: 2, cursor: 'pointer'}} onClick={() => toggle(c.id)}>
            <IconButton size="small" aria-label={expanded ? 'Recolher detalhes' : 'Expandir detalhes'} aria-expanded={expanded}
              onClick={e => { e.stopPropagation(); toggle(c.id); }} sx={{transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform .15s'}}><ExpandIcon/></IconButton>
            <Box flex={1} minWidth={0}>
              <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
                <Typography sx={{fontFamily: display, fontWeight: 700, fontSize: 18}}>{c.name}</Typography>
                <Chip size="small" color={color} label={label}/>
              </Stack>
              <Meta items={[`${c.products_count ?? 0} produto(s)`, `${c.groups.length} grupo(s)`, rhythm(c), c.next_send && `Próximo envio ${dateTime(c.next_send)}`,
                `Criada em ${new Date(c.created_at).toLocaleDateString('pt-BR')}`]}/>
            </Box>
            <Box sx={{width: {xs: 90, sm: 200}, flexShrink: 0}}>
              <Stack direction="row" justifyContent="space-between" fontSize={13} mb={.5}>
                <span><b>{c.sent}</b> de {c.total || c.total_limit}</span>
                {c.failed > 0 && <Box component="span" color="error.main" sx={{display: {xs: 'none', sm: 'inline'}}}>{c.failed} falha(s)</Box>}
              </Stack>
              <LinearProgress variant="determinate" value={c.progress} aria-label={`${c.progress}% enviado`}
                sx={{height: 6, bgcolor: tokens.paper, '& .MuiLinearProgress-bar': {bgcolor: c.failed ? tokens.danger : tokens.saving}}}/>
            </Box>
          </Box>
          <Collapse in={expanded} unmountOnExit>
            <Box sx={{px: 2, pb: 2, pt: .5, borderTop: `1px solid ${tokens.line}`}}>
              <Stack direction="row" gap={1} flexWrap="wrap" my={1.5}>
                {can.schedule && <Button size="small" variant="contained" startIcon={<PlayIcon/>} disabled={busy === c.id} onClick={() => navigate(`/campaigns/${c.id}/edit?step=6`)}>Revisar e agendar</Button>}
                {can.pause && <Tooltip title="Segura os anúncios que ainda não saíram. Nada é perdido."><Button size="small" variant="outlined" startIcon={<PauseIcon/>} disabled={busy === c.id} onClick={() => act(c, 'pause', 'Campanha pausada.')}>Pausar</Button></Tooltip>}
                {can.resume && <Tooltip title="Replaneja a partir de agora o que ainda não foi enviado."><Button size="small" variant="contained" startIcon={<PlayIcon/>} disabled={busy === c.id} onClick={() => act(c, 'resume', 'Campanha retomada.')}>Retomar</Button></Tooltip>}
                {can.edit && <Button size="small" startIcon={<EditIcon/>} component={Link} to={`/campaigns/${c.id}/edit`}>Editar</Button>}
                {can.edit && <Button size="small" startIcon={<SearchIcon/>} component={Link} to={`/campaigns/${c.id}/edit?step=2`}>Fazer nova busca</Button>}
                {can.edit && <Button size="small" startIcon={<AddIcon/>} component={Link} to={`/campaigns/${c.id}/edit?step=3`}>Ver produtos</Button>}
                <Tooltip title="Cria um rascunho com a mesma configuração."><Button size="small" startIcon={<CopyIcon/>} disabled={busy === c.id} onClick={() => act(c, 'duplicate', '')}>Duplicar</Button></Tooltip>
                {can.cancel && <Button size="small" color="error" startIcon={<StopIcon/>} disabled={busy === c.id}
                  onClick={async () => { if (await confirm.ask('Cancelar campanha?', `Os ${c.pending} anúncio(s) que ainda não saíram serão cancelados. O que já foi enviado continua no histórico.`, 'Cancelar campanha')) act(c, 'cancel', 'Campanha cancelada.'); }}>Cancelar</Button>}
                {can.remove && <Button size="small" color="error" startIcon={<DeleteIcon/>} disabled={busy === c.id}
                  onClick={async () => { if (await confirm.ask('Excluir campanha?', 'A campanha sai da lista. As publicações já enviadas continuam na Fila.', 'Excluir')) act(c, 'delete', 'Campanha excluída.'); }}>Excluir</Button>}
              </Stack>
              <Details c={c}/>
            </Box>
          </Collapse>
        </Card>;
      })}
    </Stack>
    {confirm.dialog}
  </>;
}
