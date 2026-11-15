import {useCallback, useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {Alert, Box, Button, Card, Stack, Typography} from '@mui/material';
import {api, apiError, getPage} from '../services/api';
import {extensionStatus, type ExtensionStatus} from '../services/sender';
import type {Publication, Summary} from '../types/models';
import type {Listing} from '../types/search';
import {Feedback} from '../components/Feedback';
import {Meta, PageHeader, PriceTag} from '../components/Ui';
import {display, tokens} from '../theme';

const time = (iso: string) => new Date(iso).toLocaleTimeString('pt-BR', {hour: '2-digit', minute: '2-digit'});
const dayLabel = (iso: string) => {
  const d = new Date(iso), today = new Date(), tomorrow = new Date(); tomorrow.setDate(today.getDate() + 1);
  if (d.toDateString() === today.toDateString()) return 'Hoje';
  if (d.toDateString() === tomorrow.toDateString()) return 'Amanhã';
  return d.toLocaleDateString('pt-BR', {weekday: 'long', day: 'numeric', month: 'short'});
};

function Timeline({items, ready}: {items: Publication[]; ready: Publication[]}) {
  const rows = [...ready.map(p => ({p, when: null as string | null})), ...items.map(p => ({p, when: p.scheduled_at}))];
  if (!rows.length) return <Box sx={{py: 5, textAlign: 'center'}}>
    <Typography fontWeight={600}>Nada programado para sair.</Typography>
    <Typography color="text.secondary" mt={.5} mb={2}>Aprove achados para eles entrarem na agenda do grupo.</Typography>
    <Button variant="outlined" component={Link} to="/listings">Ver achados</Button>
  </Box>;
  let lastDay = '';
  return <Box component="ol" sx={{listStyle: 'none', m: 0, p: 0}}>
    {rows.map(({p, when}) => {
      const day = when ? dayLabel(when) : 'Agora';
      const header = day !== lastDay ? (lastDay = day) : '';
      return <Box component="li" key={p.id}>
        {header && <Typography sx={{fontWeight: 650, fontSize: 13, color: 'text.secondary', mt: 2, mb: .75, }}>{header.charAt(0).toUpperCase() + header.slice(1)}</Typography>}
        <Box sx={{display: 'grid', gridTemplateColumns: '64px 14px 1fr', alignItems: 'stretch', columnGap: 1.5}}>
          <Typography sx={{fontFamily: display, fontWeight: 700, fontSize: 17, pt: 1.1, textAlign: 'right'}}>{when ? time(when) : 'Pronta'}</Typography>
          <Box sx={{position: 'relative', '&::before': {content: '""', position: 'absolute', left: 6, top: 0, bottom: 0, width: 2, bgcolor: tokens.line},
            '&::after': {content: '""', position: 'absolute', left: 1, top: 15, width: 12, height: 12, borderRadius: '50%',
              bgcolor: when ? tokens.surface : tokens.sticker, border: `2px solid ${when ? tokens.scheduled : tokens.ink}`}}}/>
          <Box sx={{py: 1, minWidth: 0, borderBottom: `1px solid ${tokens.line}`}}>
            <Typography fontWeight={600} noWrap title={p.product?.title}>{p.product?.title || `Produto ${p.product_id}`}</Typography>
            <Meta items={[p.group_name, p.product?.price != null && p.product.price.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'})]}/>
          </Box>
        </Box>
      </Box>;
    })}
  </Box>;
}

function ActionRow({count, label, to, tone}: {count?: number; label: string; to: string; tone?: 'alert' | 'deal'}) {
  const n = count ?? 0;
  return <Box component={Link} to={to} sx={{display: 'flex', alignItems: 'center', gap: 2, px: 2.5, py: 1.75, textDecoration: 'none', color: 'inherit',
    borderTop: `1px solid ${tokens.line}`, opacity: n ? 1 : .55, '&:hover': {bgcolor: tokens.paper}, '&:focus-visible': {outline: `2px solid ${tokens.ink}`, outlineOffset: -2}}}>
    <Typography sx={{fontFamily: display, fontWeight: 750, fontSize: 26, minWidth: 44, lineHeight: 1,
      color: n && tone === 'alert' ? tokens.danger : tokens.ink}}>{n}</Typography>
    <Typography flex={1} fontWeight={600}>{label}</Typography>
    {n > 0 && tone === 'deal' && <Box sx={{width: 8, height: 8, borderRadius: '50%', bgcolor: tokens.sticker, boxShadow: `0 0 0 3px ${tokens.sticker}55`}}/>}
    <Typography color="text.secondary" aria-hidden>›</Typography>
  </Box>;
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Summary>({}), [ext, setExt] = useState<ExtensionStatus | null | undefined>(undefined);
  const [scheduled, setScheduled] = useState<Publication[]>([]), [ready, setReady] = useState<Publication[]>([]);
  const [best, setBest] = useState<Listing[]>([]), [pending, setPending] = useState(0), [error, setError] = useState('');
  const load = useCallback(async () => {
    try {
      const [s, sch, q, l] = await Promise.all([
        api.get<Summary>('/publications/summary'),
        api.get<Publication[]>('/publications', {params: {status: 'scheduled', limit: 8}}),
        api.get<Publication[]>('/publications/queue', {params: {limit: 4}}),
        getPage<Listing>('/listings', {limit: 3}).catch(() => ({items: [], total: 0})),
      ]);
      setStats(s.data); setScheduled(sch.data); setReady(q.data); setBest(l.items); setPending(l.total); setError('');
    } catch (e) { setError(apiError(e, 'Não foi possível carregar o resumo do dia.')); }
  }, []);
  useEffect(() => { load(); extensionStatus().then(setExt); const t = setInterval(load, 20000); return () => clearInterval(t); }, [load]);
  const today = new Date().toLocaleDateString('pt-BR', {weekday: 'long', day: 'numeric', month: 'long'});

  return <>
    <PageHeader title="Hoje" description={today.charAt(0).toUpperCase() + today.slice(1)}
      actions={<><Button variant="outlined" component={Link} to="/searches">Buscas</Button>
        <Button variant="contained" component={Link} to="/listings">Aprovar achados{pending ? ` (${pending})` : ''}</Button></>}/>
    <Feedback error={error} onRetry={load} onClose={() => setError('')}/>
    {ext === null && <Alert severity="warning" sx={{mb: 3}}>A extensão do Autopost não respondeu neste Chrome. Sem ela não há busca no Mercado Livre
      nem envio pelo WhatsApp. Instale a pasta "extension" em chrome://extensions e aperte F5.</Alert>}

    <Box sx={{display: 'grid', gap: 3, gridTemplateColumns: {xs: '1fr', md: '1.35fr 1fr'}, alignItems: 'start'}}>
      <Card sx={{p: {xs: 2, md: 3}}}>
        <Stack direction="row" justifyContent="space-between" alignItems="baseline">
          <Typography variant="h5" component="h2">Próximos envios</Typography>
          <Button size="small" component={Link} to="/queue?tab=scheduled">Ver agenda</Button>
        </Stack>
        <Timeline items={scheduled} ready={ready}/>
      </Card>
      <Stack gap={3}>
        <Card>
          <Typography variant="h5" component="h2" sx={{px: 2.5, pt: 2.5, pb: 1.5}}>Pede sua ação</Typography>
          <ActionRow count={pending} label="Achados para aprovar" to="/listings" tone="deal"/>
          <ActionRow count={stats.awaiting_approval} label="Publicações aguardando aprovação" to="/queue?tab=awaiting_approval"/>
          <ActionRow count={stats.failed} label="Envios com falha" to="/queue?tab=failed" tone="alert"/>
          <ActionRow count={stats.needs_review} label="Produtos para revisar" to="/products?status=needs_review"/>
          <ActionRow count={stats.awaiting_browser} label="Produtos aguardando leitura" to="/products?status=awaiting_browser"/>
        </Card>
        <Stack direction="row" gap={3} px={.5}>
          {([['Enviadas', stats.sent], ['Agendadas', stats.scheduled], ['Produtos', stats.total_products]] as [string, number | undefined][]).map(([label, value]) =>
            <Box key={label}><Typography sx={{fontFamily: display, fontWeight: 750, fontSize: 24, lineHeight: 1.1}}>{value ?? 0}</Typography>
              <Typography variant="body2" color="text.secondary">{label}</Typography></Box>)}
        </Stack>
      </Stack>
    </Box>

    {best.length > 0 && <Box mt={5}>
      <Stack direction="row" justifyContent="space-between" alignItems="baseline" mb={1.5}>
        <Typography variant="h5" component="h2">Melhores achados agora</Typography>
        <Button size="small" component={Link} to="/listings">Ver todos</Button>
      </Stack>
      <Box sx={{display: 'grid', gap: 2, gridTemplateColumns: {xs: '1fr', sm: 'repeat(3, 1fr)'}}}>
        {best.map(item => <Card key={item.id} component={Link} to="/listings" sx={{p: 2, textDecoration: 'none', color: 'inherit', display: 'flex', gap: 1.75,
          '&:hover': {borderColor: tokens.ink}}}>
          <Box component="img" src={item.image_url} alt="" referrerPolicy="no-referrer" sx={{width: 64, height: 64, objectFit: 'contain', borderRadius: 2, bgcolor: '#fff', flexShrink: 0}}/>
          <Box minWidth={0}>
            <Typography fontWeight={600} fontSize={14} sx={{display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden', mb: .75}}>{item.title}</Typography>
            <PriceTag price={item.price} original={item.original_price} size="sm"/>
          </Box>
        </Card>)}
      </Box>
    </Box>}
  </>;
}
