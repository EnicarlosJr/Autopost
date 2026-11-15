import {Alert, Box, Button, LinearProgress, Typography} from '@mui/material';

/** Mensagens de erro e sucesso no topo da tela, sempre com como fechar e, no erro, como tentar de novo. */
export function Feedback({error, notice, onRetry, onClose}: {error?: string; notice?: string; onRetry?: () => void; onClose: () => void}) {
  return <>
    {error && <Alert severity="error" sx={{mb: 2}} onClose={onClose}
      action={onRetry ? <Button color="inherit" size="small" onClick={onRetry}>Tentar de novo</Button> : undefined}>{error}</Alert>}
    {notice && <Alert severity="success" sx={{mb: 2}} onClose={onClose}>{notice}</Alert>}
  </>;
}

export function Loading({show}: {show: boolean}) {
  return show ? <LinearProgress sx={{mb: 2}} aria-label="Carregando"/> : null;
}

export function Empty({text}: {text: string}) {
  return <Box sx={{py: 6, textAlign: 'center', color: 'text.secondary'}}><Typography>{text}</Typography></Box>;
}

export function LoadMore({show, onClick, loading}: {show: boolean; onClick: () => void; loading: boolean}) {
  return show ? <Box textAlign="center" mt={2}><Button onClick={onClick} disabled={loading}>Carregar mais</Button></Box> : null;
}
