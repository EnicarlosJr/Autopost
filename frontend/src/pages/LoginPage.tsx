import {useState} from 'react';
import {Alert, Box, Button, Stack, TextField, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {PriceTag} from '../components/Ui';
import {display, tokens} from '../theme';

export default function LoginPage({onLogin}: {onLogin: (token: string) => void}) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true); setError('');
    try {
      const r = await api.post('/auth/login', {email, password});
      localStorage.setItem('autopost_token', r.data.access_token);
      onLogin(r.data.access_token);
    } catch (e) { setError(apiError(e, 'Não foi possível entrar.')); }
    finally { setBusy(false); }
  };
  return <Box sx={{minHeight: '100vh', display: 'grid', gridTemplateColumns: {xs: '1fr', md: '1fr 1fr'}}}>
    <Box sx={{bgcolor: tokens.ink, color: '#fff', p: {xs: 4, md: 8}, display: {xs: 'none', md: 'flex'}, flexDirection: 'column', justifyContent: 'space-between'}}>
      <Stack direction="row" alignItems="center" gap={1.25}>
        <Box aria-hidden sx={{width: 34, height: 34, borderRadius: '9px 9px 9px 2px', bgcolor: tokens.sticker, color: tokens.ink, display: 'grid',
          placeItems: 'center', fontFamily: display, fontWeight: 800, fontSize: 19, transform: 'rotate(-4deg)'}}>%</Box>
        <Typography sx={{fontFamily: display, fontWeight: 750, fontSize: 24}}>Autopost</Typography>
      </Stack>
      <Box>
        <Typography sx={{fontFamily: display, fontWeight: 700, fontSize: 44, lineHeight: 1.05, letterSpacing: '-0.03em', maxWidth: 440}}>
          Garimpe a oferta, o grupo recebe no horário certo.</Typography>
        <Box sx={{mt: 4, display: 'inline-block', bgcolor: '#fff', color: tokens.ink, borderRadius: 3, p: 2.5, transform: 'rotate(-1.5deg)'}}>
          <Typography fontWeight={600} fontSize={14} mb={1}>Lanterna Tática Recarregável</Typography>
          <PriceTag price={53.84} original={159.9} size="lg"/>
        </Box>
      </Box>
      <Typography fontSize={13} color="rgba(255,255,255,.5)">Roda no seu computador. Busca e envia pelo seu Chrome.</Typography>
    </Box>
    <Box sx={{display: 'grid', placeItems: 'center', p: 3}}>
      <Box component="form" onSubmit={e => { e.preventDefault(); if (email && password) submit(); }} sx={{width: '100%', maxWidth: 380}}>
        <Typography variant="h4" component="h1">Entrar</Typography>
        <Typography color="text.secondary" mt={.75} mb={3}>Use o e-mail e a senha do administrador.</Typography>
        {error && <Alert severity="error" sx={{mb: 2}}>{error}</Alert>}
        <Stack spacing={2}>
          <TextField label="E-mail" autoComplete="username" autoFocus value={email} onChange={e => setEmail(e.target.value)}/>
          <TextField label="Senha" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)}/>
          <Button type="submit" size="large" variant="contained" disabled={!email || !password || busy}>{busy ? 'Entrando…' : 'Entrar'}</Button>
        </Stack>
      </Box>
    </Box>
  </Box>;
}
