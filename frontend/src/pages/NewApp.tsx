import {useEffect, useState} from 'react';
import {Link, Navigate, Route, Routes, useLocation} from 'react-router-dom';
import {Alert, Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Drawer, IconButton, Stack, TextField, Typography, useMediaQuery} from '@mui/material';
import {api, apiError, getPage} from '../services/api';
import {extensionStatus, type ExtensionStatus} from '../services/sender';
import type {Summary} from '../types/models';
import {StatusDot} from '../components/Ui';
import {display, tokens} from '../theme';
import CampaignEditor from './CampaignEditor';
import CampaignsPage from './CampaignsPage';
import DashboardPage from './DashboardPage';
import GroupsPage from './GroupsPage';
import ListingsPage from './ListingsPage';
import ProfilePage from './ProfilePage';
import LoginPage from './LoginPage';
import ProductsPage from './ProductsPage';
import QueuePage from './QueuePage';
import SearchesPage from './SearchesPage';
import SettingsPage from './SettingsPage';
import {SchoolListEditor, SchoolListsPage} from './SchoolListsPage';
import SchoolVisitorsPage from './SchoolVisitorsPage';

const DRAWER = 248;

function PasswordDialog({open, onClose}: {open: boolean; onClose: () => void}) {
  const [current, setCurrent] = useState(''), [next, setNext] = useState(''), [confirm, setConfirm] = useState('');
  const [error, setError] = useState(''), [done, setDone] = useState(false), [busy, setBusy] = useState(false);
  const reset = () => { setCurrent(''); setNext(''); setConfirm(''); setError(''); setDone(false); };
  const submit = async () => {
    if (next !== confirm) { setError('A confirmação não confere com a nova senha.'); return; }
    setBusy(true); setError('');
    try { await api.post('/auth/password', {current_password: current, new_password: next}); setDone(true); }
    catch (e) { setError(apiError(e, 'Não foi possível trocar a senha.')); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onClose={() => { reset(); onClose(); }} maxWidth="xs" fullWidth>
    <DialogTitle>Trocar senha</DialogTitle>
    <DialogContent>
      {error && <Alert severity="error" sx={{mb: 2}}>{error}</Alert>}
      {done ? <Alert severity="success">Senha trocada. Use a nova senha no próximo login.</Alert> :
        <Stack spacing={2} sx={{pt: 1}}>
          <TextField label="Senha atual" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)}/>
          <TextField label="Nova senha" type="password" autoComplete="new-password" helperText="Pelo menos 12 caracteres" value={next} onChange={e => setNext(e.target.value)}/>
          <TextField label="Confirme a nova senha" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)}/>
        </Stack>}
    </DialogContent>
    <DialogActions>
      <Button onClick={() => { reset(); onClose(); }}>{done ? 'Fechar' : 'Cancelar'}</Button>
      {!done && <Button variant="contained" disabled={busy || !current || next.length < 12} onClick={submit}>Trocar</Button>}
    </DialogActions>
  </Dialog>;
}

type Counts = {listings: number; approval: number; failed: number};
const NAV: {group: string; items: {label: string; to: string; count?: keyof Counts; alert?: boolean}[]}[] = [
  {group: 'Encontrar', items: [{label: 'Buscas', to: '/searches'}, {label: 'Achados', to: '/listings', count: 'listings'}]},
  {group: 'Publicar', items: [{label: 'Campanhas', to: '/campaigns'}, {label: 'Produtos', to: '/products'}, {label: 'Listas escolares', to: '/school-lists'}, {label: 'Fila', to: '/queue', count: 'approval'},
    {label: 'Falhas', to: '/queue?tab=failed', count: 'failed', alert: true}]},
  {group: 'Ajustes', items: [{label: 'Meu perfil', to: '/profile'}, {label: 'Grupos', to: '/groups'}, {label: 'Configurações', to: '/settings'}]},
];

function useCounts(path: string) {
  const [counts, setCounts] = useState<Counts>({listings: 0, approval: 0, failed: 0});
  const [ext, setExt] = useState<ExtensionStatus | null | undefined>(undefined);
  useEffect(() => {
    const load = async () => {
      const [summary, listings] = await Promise.all([
        api.get<Summary>('/publications/summary').then(r => r.data).catch(() => ({} as Summary)),
        getPage('/listings', {limit: 1}).then(r => r.total).catch(() => 0),
      ]);
      setCounts({listings, approval: summary.awaiting_approval || 0, failed: summary.failed || 0});
      setExt(await extensionStatus());
    };
    load(); const timer = setInterval(load, 20000); return () => clearInterval(timer);
  }, [path]);
  return {counts, ext};
}

function Sidebar({email, counts, ext, onPassword, onLogout}: {email: string; counts: Counts; ext: ExtensionStatus | null | undefined;
  onPassword: () => void; onLogout: () => void}) {
  const loc = useLocation();
  const here = loc.pathname + loc.search;
  const active = (to: string) => to.includes('?') ? here === to : to === '/' ? loc.pathname === '/' : loc.pathname.startsWith(to) && !(to === '/queue' && loc.search.includes('tab=failed'));
  const item = (label: string, to: string, count?: number, alert?: boolean) => {
    const on = active(to);
    return <Box key={to} component={Link} to={to} aria-current={on ? 'page' : undefined} sx={{
      display: 'flex', alignItems: 'center', gap: 1, px: 1.5, py: 1, borderRadius: 2, textDecoration: 'none', fontWeight: 600, fontSize: 14.5,
      color: on ? '#fff' : 'rgba(255,255,255,.66)', bgcolor: on ? 'rgba(255,255,255,.09)' : 'transparent', position: 'relative',
      '&:hover': {color: '#fff', bgcolor: 'rgba(255,255,255,.06)'},
      '&:focus-visible': {outline: `2px solid ${tokens.sticker}`, outlineOffset: 2},
      '&::before': on ? {content: '""', position: 'absolute', left: -12, top: 8, bottom: 8, width: 3, borderRadius: 3, bgcolor: tokens.sticker} : {},
    }}>
      <Box flex={1}>{label}</Box>
      {!!count && <Box component="span" sx={{fontFamily: display, fontWeight: 700, fontSize: 12.5, px: .9, py: .1, borderRadius: 6,
        bgcolor: alert ? tokens.danger : on ? tokens.sticker : 'rgba(255,255,255,.12)', color: alert ? '#fff' : on ? tokens.ink : '#fff'}}>{count}</Box>}
    </Box>;
  };
  return <Box component="nav" aria-label="Menu" sx={{bgcolor: tokens.ink, color: '#fff', height: '100%', display: 'flex', flexDirection: 'column', px: 1.5, py: 2.5}}>
    <Box component={Link} to="/" sx={{display: 'flex', alignItems: 'center', gap: 1.25, px: 1.5, mb: 3, textDecoration: 'none', color: '#fff'}}>
      <Box aria-hidden sx={{width: 30, height: 30, borderRadius: '8px 8px 8px 2px', bgcolor: tokens.sticker, color: tokens.ink, display: 'grid',
        placeItems: 'center', fontFamily: display, fontWeight: 800, fontSize: 17, transform: 'rotate(-4deg)'}}>%</Box>
      <Typography sx={{fontFamily: display, fontWeight: 750, fontSize: 21, letterSpacing: '-0.02em'}}>Autopost</Typography>
    </Box>
    {item('Hoje', '/')}
    {NAV.map(section => <Box key={section.group} mt={2.5}>
      <Typography sx={{px: 1.5, mb: .5, fontSize: 12.5, fontWeight: 600, color: 'rgba(255,255,255,.42)'}}>{section.group}</Typography>
      {section.items.map(i => item(i.label, i.to, i.count ? counts[i.count] : undefined, i.alert))}
    </Box>)}
    <Box flex={1}/>
    <Box sx={{mx: .5, p: 1.5, borderRadius: 2.5, bgcolor: 'rgba(255,255,255,.06)', display: 'grid', gap: .9, color: 'rgba(255,255,255,.85)'}}>
      {ext === undefined ? <Typography fontSize={13} color="rgba(255,255,255,.6)">Verificando a extensão…</Typography> : <>
        <StatusDot ok={Boolean(ext)} label={ext ? `Extensão ${ext.version}` : 'Extensão não encontrada'}/>
        <StatusDot ok={Boolean(ext?.whatsapp_tab)} warn={Boolean(ext)} label={ext?.whatsapp_tab ? 'WhatsApp Web aberto' : 'WhatsApp Web fechado'}/>
        <StatusDot ok={Boolean(ext?.auto_send)} warn label={ext?.auto_send ? 'Envio automático ligado' : 'Envio automático desligado'}/>
      </>}
    </Box>
    <Box sx={{mt: 1.5, px: 1.5}}>
      <Typography fontSize={13} color="rgba(255,255,255,.6)" noWrap title={email}>{email || 'Conectado'}</Typography>
      <Stack direction="row" gap={.5} ml={-1} mt={.25}>
        <Button size="small" onClick={onPassword} sx={{color: 'rgba(255,255,255,.85)'}}>Trocar senha</Button>
        <Button size="small" onClick={onLogout} sx={{color: 'rgba(255,255,255,.85)'}}>Sair</Button>
      </Stack>
    </Box>
  </Box>;
}

function Shell({email, onLogout}: {email: string; onLogout: () => void}) {
  const loc = useLocation();
  const desktop = useMediaQuery('(min-width:960px)');
  const [open, setOpen] = useState(false), [password, setPassword] = useState(false);
  const {counts, ext} = useCounts(loc.pathname + loc.search);
  useEffect(() => setOpen(false), [loc.pathname, loc.search]);
  const menu = <Sidebar email={email} counts={counts} ext={ext} onPassword={() => setPassword(true)} onLogout={onLogout}/>;
  return <>
    {desktop
      ? <Drawer variant="permanent" sx={{'& .MuiDrawer-paper': {width: DRAWER, boxSizing: 'border-box', border: 0, borderRadius: 0}}}>{menu}</Drawer>
      : <Drawer open={open} onClose={() => setOpen(false)} sx={{'& .MuiDrawer-paper': {width: DRAWER, borderRadius: 0}}}>{menu}</Drawer>}
    <Box sx={{ml: desktop ? `${DRAWER}px` : 0, minHeight: '100vh'}}>
      {!desktop && <Box sx={{position: 'sticky', top: 0, zIndex: 10, display: 'flex', alignItems: 'center', gap: 1, px: 1.5, py: 1,
        bgcolor: tokens.ink, color: '#fff'}}>
        <IconButton aria-label="Abrir menu" onClick={() => setOpen(true)} sx={{color: '#fff'}}>☰</IconButton>
        <Typography sx={{fontFamily: display, fontWeight: 750, fontSize: 19}}>Autopost</Typography>
        <Box flex={1}/>
        {ext === null && <Typography fontSize={12.5} color={tokens.sticker}>Extensão não encontrada</Typography>}
      </Box>}
      <Box component="main" sx={{maxWidth: 1240, mx: 'auto', px: {xs: 2, md: 5}, py: {xs: 3, md: 5}}}>
        <Routes>
          <Route path="/" element={<DashboardPage/>}/>
          <Route path="/products" element={<ProductsPage/>}/>
          <Route path="/queue" element={<QueuePage/>}/>
          <Route path="/settings" element={<SettingsPage/>}/>
          <Route path="/searches" element={<SearchesPage/>}/>
          <Route path="/listings" element={<ListingsPage/>}/>
          <Route path="/campaigns" element={<CampaignsPage/>}/>
          <Route path="/campaigns/new" element={<CampaignEditor key="new"/>}/>
          <Route path="/campaigns/:id/edit" element={<CampaignEditor/>}/>
          <Route path="/school-lists" element={<SchoolListsPage/>}/>
          <Route path="/school-lists/visitors" element={<SchoolVisitorsPage/>}/>
          <Route path="/school-lists/:id" element={<SchoolListEditor/>}/>
          <Route path="/groups" element={<GroupsPage/>}/>
          <Route path="/profile" element={<ProfilePage/>}/>
          <Route path="/publications" element={<Navigate to="/queue" replace/>}/>
          <Route path="/whatsapp" element={<Navigate to="/queue?tab=approved" replace/>}/>
          <Route path="/automations" element={<Navigate to="/settings" replace/>}/>
          <Route path="*" element={<Navigate to="/" replace/>}/>
        </Routes>
      </Box>
    </Box>
    <PasswordDialog open={password} onClose={() => setPassword(false)}/>
  </>;
}

export default function NewApp() {
  const [token, setToken] = useState(localStorage.getItem('autopost_token'));
  const [email, setEmail] = useState('');
  useEffect(() => { if (token) api.get('/auth/me').then(r => setEmail(r.data.email || '')).catch(() => {}); }, [token]);
  const logout = () => { localStorage.removeItem('autopost_token'); setToken(null); setEmail(''); };
  if (!token) return <LoginPage onLogin={setToken}/>;
  return <Shell email={email} onLogout={logout}/>;
}
