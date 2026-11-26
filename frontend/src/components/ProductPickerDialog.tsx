import {useEffect, useState} from 'react';
import {Box, Button, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, InputAdornment, LinearProgress, MenuItem, Stack,
  TextField, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {usePaged} from '../hooks/usePaged';
import type {Product} from '../types/product';
import type {CampaignOptions} from '../types/campaign';
import {fetchAllIds, inBatches} from './Bulk';
import {PriceTag} from './Ui';
import {SearchIcon} from './Icons';
import {tokens} from '../theme';

/** Escolher produtos já cadastrados sem sair da campanha: busca, filtros, "N de maior desconto" e adicionar. */
export default function ProductPickerDialog({open, campaignId, inCampaign, onClose, onAdded}: {open: boolean; campaignId: number;
  /** Produtos que já estão na campanha (aparecem marcados como "já na campanha"). */
  inCampaign: number[]; onClose: () => void; onAdded: (added: number) => void}) {
  const [q, setQ] = useState(''), [query, setQuery] = useState(''), [category, setCategory] = useState(''), [tag, setTag] = useState('');
  const [sort, setSort] = useState('discount'), [picked, setPicked] = useState<number[]>([]), [bestN, setBestN] = useState(30);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [facets, setFacets] = useState<CampaignOptions | null>(null);
  useEffect(() => { const t = setTimeout(() => setQuery(q.trim()), 350); return () => clearTimeout(t); }, [q]);
  useEffect(() => { if (open && !facets) api.get<CampaignOptions>('/campaigns/options').then(r => setFacets(r.data)).catch(() => {}); }, [open, facets]);
  useEffect(() => { if (!open) { setPicked([]); setError(''); } }, [open]);
  const params = {status: 'processed', q: query || undefined, category: category || undefined, tag: tag || undefined, sort};
  const list = usePaged<Product>('/products', params, 40);   // o diálogo só é montado aberto
  const taken = new Set(inCampaign);
  const toggle = (id: number) => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id]);
  const pageFree = list.items.filter(p => !taken.has(p.id));
  const allPage = pageFree.length > 0 && pageFree.every(p => picked.includes(p.id));

  const pickBest = async () => {
    setBusy(true); setError('');
    try {
      const ids = await fetchAllIds('/products', {...params, sort: 'discount'}, Math.ceil((bestN + inCampaign.length) / 200) * 200);
      setPicked(ids.filter(id => !taken.has(id)).slice(0, bestN));
    } catch (e) { setError(apiError(e, 'Não foi possível selecionar os melhores.')); }
    finally { setBusy(false); }
  };
  const add = async () => {
    setBusy(true); setError('');
    try {
      const r = await inBatches(picked, chunk => api.post(`/campaigns/${campaignId}/products`, {product_ids: chunk}), 500);
      onAdded(r.added ?? picked.length); setPicked([]); onClose();
    } catch (e) { setError(apiError(e, 'Não foi possível adicionar à campanha.')); }
    finally { setBusy(false); }
  };

  return <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="md" fullWidth scroll="paper">
    <DialogTitle>Escolher dos meus produtos</DialogTitle>
    <DialogContent dividers>
      <Stack direction={{xs: 'column', sm: 'row'}} gap={1} mb={1.5}>
        <TextField size="small" placeholder="Buscar pelo nome" value={q} onChange={e => setQ(e.target.value)} sx={{flex: 2}}
          InputProps={{startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small"/></InputAdornment>}}/>
        <TextField select size="small" label="Categoria" value={category} onChange={e => setCategory(e.target.value)} sx={{flex: 1, minWidth: 140}}>
          <MenuItem value="">Todas</MenuItem>{facets?.categories.map(c => <MenuItem key={c.name} value={c.name}>{c.name} ({c.count})</MenuItem>)}</TextField>
        <TextField select size="small" label="Tag" value={tag} onChange={e => setTag(e.target.value)} sx={{flex: 1, minWidth: 120}}>
          <MenuItem value="">Todas</MenuItem>{facets?.tags.map(c => <MenuItem key={c.name} value={c.name}>{c.name} ({c.count})</MenuItem>)}</TextField>
        <TextField select size="small" label="Ordenar" value={sort} onChange={e => setSort(e.target.value)} sx={{minWidth: 150}}>
          <MenuItem value="discount">Maior desconto</MenuItem><MenuItem value="newest">Mais recentes</MenuItem>
          <MenuItem value="price_asc">Menor preço</MenuItem><MenuItem value="price_desc">Maior preço</MenuItem></TextField>
      </Stack>
      <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" mb={1}>
        <TextField size="small" type="number" label="Quantos" value={bestN} sx={{width: 90}}
          onChange={e => setBestN(Math.max(1, Math.min(500, Number(e.target.value) || 1)))}/>
        <Button variant="outlined" disabled={busy} onClick={pickBest}>Marcar os {bestN} de maior desconto</Button>
        <Box flex={1}/>
        <Typography variant="body2" color="text.secondary">{list.total} pronto(s){query || category || tag ? ' com esses filtros' : ''}</Typography>
      </Stack>
      {pageFree.length > 0 && <Stack direction="row" alignItems="center" mb={.5}>
        <Checkbox checked={allPage} onChange={() => setPicked(p => allPage ? p.filter(id => !pageFree.some(x => x.id === id))
          : [...new Set([...p, ...pageFree.map(x => x.id)])])} inputProps={{'aria-label': 'Marcar os desta lista'}}/>
        <Typography variant="body2">Marcar os {pageFree.length} desta lista</Typography>
      </Stack>}
      {list.loading && <LinearProgress sx={{mb: 1}}/>}
      {(error || list.error) && <Typography color="error" fontSize={14} mb={1}>{error || list.error}</Typography>}
      {!list.loading && !list.items.length && <Typography color="text.secondary" py={3} textAlign="center">Nenhum produto pronto com esses filtros.</Typography>}
      <Stack gap={.75}>{list.items.map(p => { const done = taken.has(p.id), on = picked.includes(p.id);
        return <Stack key={p.id} direction="row" gap={1.25} alignItems="center" onClick={() => !done && toggle(p.id)}
          sx={{p: .75, borderRadius: 2, border: `1px solid ${on ? 'currentColor' : tokens.line}`, color: on ? 'primary.main' : 'inherit',
            cursor: done ? 'default' : 'pointer', opacity: done ? .55 : 1}}>
          <Checkbox size="small" checked={on || done} disabled={done} onClick={e => e.stopPropagation()} onChange={() => toggle(p.id)}
            inputProps={{'aria-label': `Marcar ${p.title}`}}/>
          {p.image_url ? <Box component="img" src={p.image_url} alt="" sx={{width: 52, height: 52, objectFit: 'contain', borderRadius: 1.5, bgcolor: '#fff', flex: 'none'}}/>
            : <Box sx={{width: 52, height: 52, borderRadius: 1.5, bgcolor: 'background.default', flex: 'none'}}/>}
          <Box flex={1} minWidth={0} color="text.primary">
            <Typography fontSize={14} fontWeight={600} noWrap title={p.title}>{p.title || 'Sem nome'}</Typography>
            <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
              <PriceTag price={p.price} original={p.original_price} note={p.price_note}/>
              {p.category && <Typography variant="caption" color="text.secondary">{p.category}</Typography>}
              {done && <Chip size="small" label="já na campanha"/>}
            </Stack>
          </Box>
        </Stack>; })}</Stack>
      {list.hasMore && <Box textAlign="center" mt={1.5}><Button disabled={list.loading} onClick={list.loadMore}>Carregar mais</Button></Box>}
    </DialogContent>
    <DialogActions>
      {picked.length > 0 && <Button onClick={() => setPicked([])} disabled={busy}>Limpar ({picked.length})</Button>}
      <Box flex={1}/>
      <Button onClick={onClose} disabled={busy}>Cancelar</Button>
      <Button variant="contained" disabled={busy || !picked.length} onClick={add}>
        {picked.length ? `Adicionar ${picked.length} à campanha` : 'Marque os produtos'}</Button>
    </DialogActions>
  </Dialog>;
}
