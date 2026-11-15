import type {ReactNode} from 'react';
import {Box, Stack, Typography} from '@mui/material';
import {display, tokens} from '../theme';

/** Cabeçalho das telas: título, uma linha dizendo para que serve e as ações à direita. */
export function PageHeader({title, description, actions}: {title: string; description?: ReactNode; actions?: ReactNode}) {
  return <Stack direction={{xs: 'column', sm: 'row'}} justifyContent="space-between" alignItems={{sm: 'flex-end'}} gap={2} mb={3}>
    <Box minWidth={0}>
      <Typography variant="h4" component="h1">{title}</Typography>
      {description && <Typography color="text.secondary" mt={.75} maxWidth={640}>{description}</Typography>}
    </Box>
    {actions && <Stack direction="row" gap={1} flexWrap="wrap" flexShrink={0}>{actions}</Stack>}
  </Stack>;
}

/** Informações secundárias lado a lado, separadas por espaço (sem pontos ou traços). */
export function Meta({items}: {items: (ReactNode | false | null | undefined | '')[]}) {
  const visible = items.filter(Boolean);
  if (!visible.length) return null;
  return <Stack direction="row" flexWrap="wrap" columnGap={2} rowGap={.25} sx={{color: 'text.secondary', fontSize: 13}}>
    {visible.map((item, i) => <span key={i}>{item}</span>)}
  </Stack>;
}

const brl = (n: number) => n.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});

/**
 * Etiqueta de preço: o elemento marcante do Autopost. Preço "Por" grande, "De" riscado
 * e o desconto num adesivo amarelo com furo de pendurar.
 */
export function PriceTag({price, original, note, size = 'md'}: {price: number | null; original?: number | null; note?: string; size?: 'sm' | 'md' | 'lg'}) {
  if (price == null) return <Typography color="text.secondary" fontSize={13}>Sem preço lido</Typography>;
  const off = original != null && original > price ? Math.floor((original - price) * 100 / original) : null;
  const fs = {sm: 18, md: 22, lg: 30}[size];
  return <Stack direction="row" alignItems="center" gap={1.25} flexWrap="wrap">
    <Box>
      {off != null && <Typography component="s" sx={{display: 'block', color: 'text.secondary', fontSize: fs * .55, lineHeight: 1.1}}>
        De {brl(original!)}</Typography>}
      <Typography sx={{fontFamily: display, fontWeight: 750, fontSize: fs, lineHeight: 1.1, letterSpacing: '-0.02em'}}>
        {brl(price)}{note && <Typography component="span" sx={{fontFamily: 'inherit', fontWeight: 500, fontSize: fs * .5, color: 'text.secondary', ml: .75, letterSpacing: 0}}>{note}</Typography>}
      </Typography>
    </Box>
    {off != null && <Box aria-label={`${off}% de desconto`} sx={{
      position: 'relative', bgcolor: tokens.sticker, color: tokens.ink, fontFamily: display, fontWeight: 800,
      fontSize: fs * .62, lineHeight: 1, py: .6, pl: 2, pr: 1, borderRadius: '4px 8px 8px 4px',
      clipPath: 'polygon(10px 0, 100% 0, 100% 100%, 10px 100%, 0 50%)', transform: 'rotate(-3deg)',
      '&::before': {content: '""', position: 'absolute', left: 9, top: '50%', width: 5, height: 5, mt: '-2.5px',
        borderRadius: '50%', bgcolor: tokens.surface},
    }}>−{off}%</Box>}
  </Stack>;
}

/** Ponto de estado com texto (extensão, WhatsApp, envio automático). */
export function StatusDot({ok, label, warn}: {ok: boolean; label: ReactNode; warn?: boolean}) {
  const color = ok ? '#3DDC97' : warn ? tokens.sticker : '#FF8A80';
  return <Stack direction="row" alignItems="center" gap={1} sx={{fontSize: 13}}>
    <Box sx={{width: 8, height: 8, borderRadius: '50%', bgcolor: color, boxShadow: ok ? `0 0 0 3px ${color}33` : 'none', flexShrink: 0}}/>
    <span>{label}</span>
  </Stack>;
}
