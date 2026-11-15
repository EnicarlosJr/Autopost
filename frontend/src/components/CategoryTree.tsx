import {useCallback, useEffect, useRef, useState} from 'react';
import {Box, Button, Checkbox, Chip, CircularProgress, IconButton, InputAdornment, Stack, TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {CategoryPick, MlCategory} from '../types/catalog';
import {ExpandIcon, SearchIcon} from './Icons';
import {tokens} from '../theme';

const Star = ({on}: {on: boolean}) => <Box component="span" aria-hidden sx={{fontSize: 17, lineHeight: 1, color: on ? '#E0A800' : tokens.line}}>{on ? '★' : '☆'}</Box>;

/** Selo que deixa claro que o item vem do Mercado Livre (e não foi criado pelo usuário). */
export function OfficialChip({cat, onDelete, onToggleChildren}: {cat: CategoryPick; onDelete?: () => void; onToggleChildren?: () => void}) {
  return <Chip size="small" variant="outlined" onDelete={onDelete} sx={{maxWidth: '100%', height: 'auto', py: .4, '& .MuiChip-label': {whiteSpace: 'normal'}}}
    label={<Box component="span" sx={{display: 'inline-flex', alignItems: 'center', gap: .75, flexWrap: 'wrap'}}>
      <Box component="span" sx={{fontSize: 10.5, fontWeight: 800, px: .6, borderRadius: 1, bgcolor: tokens.paper, color: tokens.muted}}>ML</Box>
      <span title={cat.path}>{cat.name || cat.id}</span>
      {!cat.is_leaf && onToggleChildren && <Box component="span" onClick={e => { e.stopPropagation(); onToggleChildren(); }}
        sx={{fontSize: 11.5, color: cat.include_children ? 'success.main' : 'text.secondary', cursor: 'pointer', textDecoration: 'underline dotted'}}>
        {cat.include_children ? '+ subcategorias' : 'só esta'}</Box>}
      {cat.active === false && <Box component="span" sx={{fontSize: 11, color: 'warning.main'}}>inativa</Box>}
    </Box>}/>;
}

type Props = {
  /** Categorias marcadas (modo de seleção). Sem onChange, a árvore só navega e favorita. */
  selected?: CategoryPick[]; onChange?: (v: CategoryPick[]) => void; height?: number;
};

export default function CategoryTree({selected = [], onChange, height = 420}: Props) {
  const [roots, setRoots] = useState<MlCategory[] | null>(null), [children, setChildren] = useState<Record<string, MlCategory[]>>({});
  const [open, setOpen] = useState<string[]>([]), [loadingId, setLoadingId] = useState(''), [error, setError] = useState('');
  const [query, setQuery] = useState(''), [results, setResults] = useState<MlCategory[] | null>(null), [searching, setSearching] = useState(false);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const selectable = Boolean(onChange);
  const picked = new Map(selected.map(s => [s.id, s]));

  useEffect(() => {
    api.get<MlCategory[]>('/ml-categories/children').then(r => { setRoots(r.data); setFavorites(new Set(r.data.filter(c => c.favorite).map(c => c.id))); })
      .catch(e => setError(apiError(e, 'Não foi possível carregar as categorias.')));
    api.get<MlCategory[]>('/ml-categories/favorites').then(r => setFavorites(new Set(r.data.map(c => c.id)))).catch(() => {});
  }, []);
  // Pesquisa instantânea (meio segundo depois da última tecla).
  const seq = useRef(0);
  useEffect(() => {
    const term = query.trim(); const mine = ++seq.current;
    if (term.length < 2) { setResults(null); return; }
    setSearching(true);
    const t = setTimeout(() => api.get<MlCategory[]>('/ml-categories/search', {params: {q: term}})
      .then(r => { if (mine === seq.current) setResults(r.data); }).catch(() => {}).finally(() => { if (mine === seq.current) setSearching(false); }), 300);
    return () => clearTimeout(t);
  }, [query]);

  const expand = useCallback(async (c: MlCategory) => {
    if (open.includes(c.id)) { setOpen(o => o.filter(x => x !== c.id)); return; }
    if (!children[c.id]) {
      setLoadingId(c.id);
      try { const r = await api.get<MlCategory[]>('/ml-categories/children', {params: {parent: c.id}}); setChildren(old => ({...old, [c.id]: r.data})); }
      catch (e) { setError(apiError(e, 'Não foi possível abrir a categoria.')); return; }
      finally { setLoadingId(''); }
    }
    setOpen(o => [...o, c.id]);
  }, [open, children]);
  const toggleFavorite = async (c: MlCategory) => {
    const on = favorites.has(c.id);
    try { await (on ? api.delete(`/ml-categories/favorites/${c.id}`) : api.put(`/ml-categories/favorites/${c.id}`));
      setFavorites(f => { const n = new Set(f); if (on) n.delete(c.id); else n.add(c.id); return n; }); }
    catch (e) { setError(apiError(e, 'Não foi possível atualizar a favorita.')); }
  };
  const toggle = (c: MlCategory) => {
    if (!onChange) return;
    onChange(picked.has(c.id) ? selected.filter(s => s.id !== c.id)
      : [...selected, {id: c.id, include_children: !c.is_leaf, name: c.name, path: c.path, is_leaf: c.is_leaf, active: c.active}]);
  };
  // Categoria já coberta por um ancestral marcado com "+ subcategorias".
  const coveredBy = (c: MlCategory) => c.path_ids.slice(0, -1).find(id => picked.get(id)?.include_children);

  const row = (c: MlCategory, depth: number, showPath = false) => {
    const isOpen = open.includes(c.id), covered = coveredBy(c);
    return <Box key={c.id}>
      <Stack direction="row" alignItems="center" gap={.5} sx={{pl: depth * 2.25, pr: 1, py: .25, '&:hover': {bgcolor: tokens.paper}, borderRadius: 1.5}}>
        <IconButton size="small" disabled={c.is_leaf} onClick={() => expand(c)} aria-label={isOpen ? `Recolher ${c.name}` : `Expandir ${c.name}`} aria-expanded={isOpen}
          sx={{visibility: c.is_leaf ? 'hidden' : 'visible', transform: isOpen ? 'none' : 'rotate(-90deg)', transition: 'transform .12s'}}>
          {loadingId === c.id ? <CircularProgress size={14}/> : <ExpandIcon fontSize="small"/>}</IconButton>
        {selectable && <Checkbox size="small" checked={picked.has(c.id) || Boolean(covered)} disabled={Boolean(covered)} onChange={() => toggle(c)}
          inputProps={{'aria-label': `Selecionar ${c.name}`}} sx={{p: .5}}/>}
        <Box flex={1} minWidth={0} sx={{cursor: c.is_leaf ? 'default' : 'pointer'}} onClick={() => !c.is_leaf && expand(c)}>
          <Typography fontSize={14.5} fontWeight={depth === 0 && !showPath ? 650 : 500} noWrap title={c.path}>{c.name}</Typography>
          {showPath && <Typography variant="caption" noWrap display="block" title={c.path}>{c.path}</Typography>}
        </Box>
        {c.is_leaf && <Chip size="small" variant="outlined" label="final" sx={{height: 20, fontSize: 11}}/>}
        <Typography variant="caption" sx={{fontFamily: 'monospace', display: {xs: 'none', sm: 'block'}}}>{c.id}</Typography>
        <Tooltip title={favorites.has(c.id) ? 'Tirar das favoritas' : 'Marcar como favorita'}>
          <IconButton size="small" onClick={() => toggleFavorite(c)} aria-label={favorites.has(c.id) ? `Tirar ${c.name} das favoritas` : `Favoritar ${c.name}`}>
            <Star on={favorites.has(c.id)}/></IconButton></Tooltip>
      </Stack>
      {isOpen && (children[c.id] || []).map(k => row(k, depth + 1))}
    </Box>;
  };

  return <Box>
    {selectable && <Box mb={1.5}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" mb={.75}>
        <Typography fontSize={14} fontWeight={600}>{selected.length ? `${selected.length} categoria(s) oficial(is) selecionada(s)` : 'Nenhuma categoria selecionada'}</Typography>
        {selected.length > 0 && <Button size="small" onClick={() => onChange!([])}>Limpar seleção</Button>}
      </Stack>
      <Stack direction="row" gap={.75} flexWrap="wrap">{selected.map(s => <OfficialChip key={s.id} cat={s}
        onDelete={() => onChange!(selected.filter(x => x.id !== s.id))}
        onToggleChildren={() => onChange!(selected.map(x => x.id === s.id ? {...x, include_children: !x.include_children} : x))}/>)}</Stack>
    </Box>}
    <TextField fullWidth size="small" placeholder="Pesquisar categoria pelo nome ou ID (ex.: SSD, MLB1672)" value={query} onChange={e => setQuery(e.target.value)}
      InputProps={{startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small"/></InputAdornment>,
        endAdornment: searching ? <CircularProgress size={16}/> : undefined}}/>
    {error && <Typography color="error" fontSize={13} mt={1}>{error}</Typography>}
    <Box sx={{mt: 1, border: `1px solid ${tokens.line}`, borderRadius: 2, height, overflow: 'auto', p: .5}}>
      {results ? (results.length ? results.map(c => row(c, 0, true)) : <Typography p={2} color="text.secondary">Nenhuma categoria com esse nome.</Typography>)
        : roots === null ? <Typography p={2} color="text.secondary">Carregando…</Typography>
        : roots.length ? roots.map(c => row(c, 0))
        : <Typography p={2} color="text.secondary">O catálogo ainda está vazio. Em Meu perfil, clique em "Atualizar categorias do Mercado Livre".</Typography>}
    </Box>
  </Box>;
}

