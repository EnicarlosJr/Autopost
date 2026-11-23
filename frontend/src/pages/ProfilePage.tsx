import {useCallback, useEffect, useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Alert, Box, Button, Card, Checkbox, Chip, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, LinearProgress, Stack, Tab, Tabs,
  TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography, useMediaQuery} from '@mui/material';
import {api, apiError} from '../services/api';
import {syncCategoriesInBrowser} from '../services/sender';
import type {CatalogStatus, CategoryPick, MlCategory, Niche} from '../types/catalog';
import CategoryTree, {OfficialChip} from '../components/CategoryTree';
import {BulkBar, MultiPick, SelectAll, eachItem, useConfirm, useSelection} from '../components/Bulk';
import {Empty, Feedback, Loading} from '../components/Feedback';
import {PageHeader} from '../components/Ui';
import StyleSettings from '../components/StyleSettings';
import {AddIcon, CopyIcon, DeleteIcon, EditIcon, RefreshIcon, TagIcon} from '../components/Icons';
import {display, tokens} from '../theme';

const SUGGESTIONS = ['Informática', 'Eletrônicos', 'Casa e Decoração', 'Ferramentas', 'Games', 'Academia e Fitness', 'Beleza', 'Acessórios', 'Eletrodomésticos'];
type Gender = 'any' | 'male' | 'female';
const GENDERS: [Gender, string][] = [['any', 'Todos'], ['male', 'Masculino'], ['female', 'Feminino']];
type Draft = {id?: number; name: string; description: string; favorite: boolean; categories: CategoryPick[]; tags: string[]; include_keywords: string[]; exclude_keywords: string[]; gender: Gender};
const EMPTY: Draft = {name: '', description: '', favorite: false, categories: [], tags: [], include_keywords: [], exclude_keywords: [], gender: 'any'};
const date = (iso: string) => new Date(iso).toLocaleDateString('pt-BR', {day: '2-digit', month: '2-digit', year: 'numeric'});

function NicheDialog({draft, onClose, onSaved}: {draft: Draft | null; onClose: () => void; onSaved: (text: string) => void}) {
  const [value, setValue] = useState<Draft | null>(draft), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const full = !useMediaQuery('(min-width:900px)');
  useEffect(() => { setValue(draft); setError(''); }, [draft]);
  if (!value) return null;
  const set = (patch: Partial<Draft>) => setValue({...value, ...patch});
  const save = async () => {
    setBusy(true); setError('');
    try {
      const body = {...value, categories: value.categories.map(c => ({id: c.id, include_children: c.include_children}))};
      if (value.id) await api.put(`/niches/${value.id}`, body); else await api.post('/niches', body);
      onSaved(value.id ? 'Nicho atualizado.' : 'Nicho criado.');
    } catch (e) { setError(apiError(e, 'Não foi possível salvar o nicho.')); }
    finally { setBusy(false); }
  };
  return <Dialog open onClose={onClose} maxWidth="lg" fullWidth fullScreen={full}>
    <DialogTitle>{value.id ? 'Editar nicho' : 'Novo nicho'}</DialogTitle>
    <DialogContent>
      {error && <Alert severity="error" sx={{mb: 2}}>{error}</Alert>}
      <Box sx={{display: 'grid', gap: 3, gridTemplateColumns: {xs: '1fr', md: '1fr 1.2fr'}, pt: 1}}>
        <Stack gap={2}>
          <TextField label="Nome do nicho" value={value.name} onChange={e => set({name: e.target.value})} autoFocus/>
          {!value.id && !value.name && <Stack direction="row" gap={.5} flexWrap="wrap">{SUGGESTIONS.map(s =>
            <Chip key={s} size="small" variant="outlined" label={s} onClick={() => set({name: s})}/>)}</Stack>}
          <TextField label="Descrição (opcional)" value={value.description} onChange={e => set({description: e.target.value})} multiline minRows={2}/>
          <Box>
            <Typography fontWeight={600} mb={.5}>Público</Typography>
            <ToggleButtonGroup exclusive size="small" value={value.gender} aria-label="Público do nicho" onChange={(_, v: Gender | null) => v && set({gender: v})}
              sx={{'& .MuiToggleButton-root': {textTransform: 'none', px: 2}}}>
              {GENDERS.map(([g, label]) => <ToggleButton key={g} value={g}>{label}</ToggleButton>)}
            </ToggleButtonGroup>
            <Typography variant="caption" display="block" mt={.5}>Nas buscas das campanhas, o público entra na palavra buscada e o outro público fica de fora.</Typography>
          </Box>
          <Box>
            <Typography fontWeight={600} mb={.5}>Criado por você</Typography>
            <Typography variant="body2" color="text.secondary" mb={1.5}>Tags e palavras-chave são suas. Elas não substituem as categorias oficiais.</Typography>
            <Stack gap={2}>
              <MultiPick label="Tags pessoais" value={value.tags} onChange={v => set({tags: v})} options={[]} helper="Ex.: oportunidade, presente, lançamento"/>
              <MultiPick label="Palavras-chave incluídas" value={value.include_keywords} onChange={v => set({include_keywords: v})} options={[]}
                helper="Usadas nas buscas de produtos (ex.: notebook, SSD, memória RAM)"/>
              <MultiPick label="Palavras-chave excluídas" value={value.exclude_keywords} onChange={v => set({exclude_keywords: v})} options={[]}
                helper="Anúncios com essas palavras no título ficam de fora (ex.: usado, recondicionado)"/>
            </Stack>
          </Box>
        </Stack>
        <Box>
          <Typography fontWeight={600} mb={.5}>Categorias oficiais do Mercado Livre</Typography>
          <Typography variant="body2" color="text.secondary" mb={1.5}>Marque uma categoria e escolha se as subcategorias entram junto (clique em "+ subcategorias" no chip).</Typography>
          <CategoryTree selected={value.categories} onChange={v => set({categories: v})} height={full ? 360 : 420}/>
        </Box>
      </Box>
    </DialogContent>
    <DialogActions><Button onClick={onClose}>Cancelar</Button>
      <Button variant="contained" disabled={busy || !value.name.trim()} onClick={save}>{value.id ? 'Salvar nicho' : 'Criar nicho'}</Button></DialogActions>
  </Dialog>;
}

function NicheCard({n, selected, onToggle, onEdit, onAction}: {n: Niche; selected: boolean; onToggle: () => void; onEdit: () => void;
  onAction: (action: 'favorite' | 'duplicate' | 'delete') => void}) {
  return <Card sx={{p: 2.25, display: 'flex', flexDirection: 'column', gap: 1.25, borderColor: selected ? 'primary.main' : undefined}}>
    <Stack direction="row" alignItems="flex-start" gap={1}>
      <Checkbox checked={selected} onChange={onToggle} sx={{m: -1}} inputProps={{'aria-label': `Selecionar ${n.name}`}}/>
      <Box flex={1} minWidth={0}>
        <Typography sx={{fontFamily: display, fontWeight: 700, fontSize: 18}}>{n.name}</Typography>
        {n.description && <Typography variant="body2" color="text.secondary">{n.description}</Typography>}
      </Box>
      <Tooltip title={n.favorite ? 'Tirar dos favoritos' : 'Marcar como favorito'}>
        <IconButton onClick={() => onAction('favorite')} aria-label={n.favorite ? 'Tirar dos favoritos' : 'Marcar como favorito'}
          sx={{color: n.favorite ? '#E0A800' : tokens.line, fontSize: 22}}>{n.favorite ? '★' : '☆'}</IconButton></Tooltip>
    </Stack>
    <Stack direction="row" gap={.5} flexWrap="wrap">
      {n.categories.length ? n.categories.map(c => <OfficialChip key={c.id} cat={c}/>) : <Typography variant="caption">Sem categorias oficiais</Typography>}
    </Stack>
    {(n.tags.length > 0 || n.include_keywords.length > 0 || n.exclude_keywords.length > 0 || (n.gender && n.gender !== 'any')) && <Stack gap={.5} fontSize={13.5}>
      {n.tags.length > 0 && <Stack direction="row" gap={.5} flexWrap="wrap">{n.tags.map(t => <Chip key={t} size="small" icon={<TagIcon sx={{fontSize: 14}}/>} label={t}/>)}</Stack>}
      {n.gender && n.gender !== 'any' && <span>Público {n.gender === 'male' ? 'masculino' : 'feminino'}</span>}
      {n.include_keywords.length > 0 && <span>Palavras: {n.include_keywords.join(', ')}</span>}
      {n.exclude_keywords.length > 0 && <Box component="span" color="text.secondary">Sem: {n.exclude_keywords.join(', ')}</Box>}
    </Stack>}
    <Box flex={1}/>
    <Stack direction="row" alignItems="center" gap={.5} sx={{borderTop: `1px solid ${tokens.line}`, pt: 1}}>
      <Typography variant="caption" flex={1}>Atualizado em {date(n.updated_at)}</Typography>
      <Tooltip title="Editar"><IconButton size="small" aria-label="Editar" onClick={onEdit}><EditIcon fontSize="small"/></IconButton></Tooltip>
      <Tooltip title="Duplicar"><IconButton size="small" aria-label="Duplicar" onClick={() => onAction('duplicate')}><CopyIcon fontSize="small"/></IconButton></Tooltip>
      <Tooltip title="Excluir"><IconButton size="small" aria-label="Excluir" onClick={() => onAction('delete')}><DeleteIcon fontSize="small"/></IconButton></Tooltip>
    </Stack>
  </Card>;
}

export default function ProfilePage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('tab') === 'categories' ? 'categories' : params.get('tab') === 'style' ? 'style' : 'niches';
  const [niches, setNiches] = useState<Niche[]>([]), [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<CatalogStatus | null>(null), [favorites, setFavorites] = useState<MlCategory[]>([]);
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [syncing, setSyncing] = useState('');
  const [draft, setDraft] = useState<Draft | null>(null), [treeKey, setTreeKey] = useState(0);
  const confirm = useConfirm(); const sel = useSelection();
  const load = useCallback(async () => {
    try {
      const [n, s, f] = await Promise.all([api.get<Niche[]>('/niches'), api.get<CatalogStatus>('/ml-categories/status'), api.get<MlCategory[]>('/ml-categories/favorites')]);
      setNiches(n.data); setStatus(s.data); setFavorites(f.data); setError('');
    } catch (e) { setError(apiError(e, 'Não foi possível carregar o perfil.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const sync = async () => {
    setError(''); setNotice(''); setSyncing('Tentando pelo servidor…');
    let result;
    try { result = (await api.post('/ml-categories/sync')).data; }
    catch {
      setSyncing('O Mercado Livre não liberou o servidor. Baixando pelo seu Chrome (cerca de 30 MB)…');
      try { result = await syncCategoriesInBrowser(); }
      catch (e) { setError(apiError(e, 'Não foi possível atualizar as categorias.')); setSyncing(''); return; }
    }
    setSyncing(''); setNotice(`Categorias atualizadas: ${result.total} no total, ${result.roots} principais, ${result.created} novas${result.inactivated ? `, ${result.inactivated} inativadas` : ''}.`);
    setTreeKey(k => k + 1); load();
  };
  const action = async (n: Niche, kind: 'favorite' | 'duplicate' | 'delete') => {
    setError(''); setNotice('');
    try {
      if (kind === 'delete') {
        if (!await confirm.ask(`Excluir o nicho "${n.name}"?`, 'Campanhas que já usaram este nicho não mudam: elas guardam uma cópia das configurações.', 'Excluir nicho')) return;
        await api.delete(`/niches/${n.id}`); setNotice('Nicho excluído.');
      } else if (kind === 'duplicate') { await api.post(`/niches/${n.id}/duplicate`); setNotice('Nicho duplicado.'); }
      else await api.post(`/niches/${n.id}/favorite`);
      load();
    } catch (e) { setError(apiError(e, 'Ação não concluída.')); }
  };
  const bulkDelete = async () => {
    if (!await confirm.ask(`Excluir ${sel.count} nicho(s)?`, 'Campanhas que já usaram estes nichos não mudam: elas guardam uma cópia das configurações.', 'Excluir nichos')) return;
    setError(''); setNotice('');
    const r = await eachItem(niches.filter(n => sel.has(n.id)), n => api.delete(`/niches/${n.id}`));
    setNotice(`${r.ok} nicho(s) excluído(s).${r.failed ? ` ${r.failed} falharam.` : ''}`); sel.clear(); load();
  };
  const edit = (n: Niche) => setDraft({id: n.id, name: n.name, description: n.description, favorite: n.favorite, categories: n.categories,
    tags: n.tags, include_keywords: n.include_keywords, exclude_keywords: n.exclude_keywords, gender: n.gender ?? 'any'});
  const catalogEmpty = status !== null && status.total === 0;

  return <>
    <PageHeader title="Meu perfil" description="Nichos, categorias favoritas e o padrão da mensagem e da foto que você reaproveita nas buscas e campanhas."
      actions={tab === 'niches' ? <Button variant="contained" startIcon={<AddIcon/>} disabled={catalogEmpty} onClick={() => setDraft({...EMPTY})}>Novo nicho</Button> : undefined}/>
    <Tabs value={tab} onChange={(_, v) => setParams(v === 'niches' ? {} : {tab: v})} sx={{mb: 2.5, borderBottom: 1, borderColor: 'divider'}}>
      <Tab value="niches" label={`Nichos${niches.length ? ` (${niches.length})` : ''}`}/>
      <Tab value="categories" label="Categorias do Mercado Livre"/>
      <Tab value="style" label="Mensagem e foto"/>
    </Tabs>
    <Feedback error={error} notice={notice} onRetry={load} onClose={() => { setError(''); setNotice(''); }}/>
    <Loading show={loading}/>
    {catalogEmpty && <Alert severity="info" sx={{mb: 2}} action={<Button color="inherit" disabled={Boolean(syncing)} onClick={sync}>Atualizar agora</Button>}>
      O catálogo de categorias oficiais ainda não foi carregado. Ele é necessário para criar nichos.</Alert>}

    {tab === 'niches' && !loading && niches.length > 0 && <SelectAll total={niches.length} selected={sel.count} onAll={() => sel.setAll(niches.map(n => n.id))} onNone={sel.clear}/>}
    {tab === 'niches' && !loading && (niches.length ? <Box sx={{display: 'grid', gap: 2, gridTemplateColumns: {xs: '1fr', sm: '1fr 1fr', lg: '1fr 1fr 1fr'}}}>
      {niches.map(n => <NicheCard key={n.id} n={n} selected={sel.has(n.id)} onToggle={() => sel.toggle(n.id)} onEdit={() => edit(n)} onAction={k => action(n, k)}/>)}</Box>
      : !catalogEmpty && <Empty text="Nenhum nicho ainda. Crie um nicho com as categorias e palavras-chave que você mais usa, como Informática ou Casa e Decoração."/>)}

    {tab === 'categories' && <Box sx={{display: 'grid', gap: 3, gridTemplateColumns: {xs: '1fr', md: '1.4fr 1fr'}, alignItems: 'start'}}>
      <Card sx={{p: 2.5}}>
        <Stack direction={{xs: 'column', sm: 'row'}} justifyContent="space-between" gap={1} mb={2}>
          <Box>
            <Typography variant="h6" component="h2">Catálogo oficial</Typography>
            <Typography variant="body2" color="text.secondary">
              {status?.total ? `${status.total.toLocaleString('pt-BR')} categorias, ${status.roots} principais. Atualizado em ${status.synced_at ? new Date(status.synced_at).toLocaleString('pt-BR') : 'data desconhecida'}.` : 'Ainda não carregado.'}</Typography>
          </Box>
          <Button variant="outlined" startIcon={<RefreshIcon/>} disabled={Boolean(syncing)} onClick={sync}>Atualizar categorias do Mercado Livre</Button>
        </Stack>
        {syncing && <Box mb={2}><Typography variant="body2" mb={.5}>{syncing}</Typography><LinearProgress/></Box>}
        <Typography variant="body2" color="text.secondary" mb={1.5}>Nomes e IDs exatamente como o Mercado Livre informa. Use a estrela para guardar as categorias que você mais usa.</Typography>
        <CategoryTree key={treeKey} height={520}/>
      </Card>
      <Card sx={{p: 2.5}}>
        <Typography variant="h6" component="h2" mb={1}>Favoritas</Typography>
        {favorites.length ? <Stack gap={1}>{favorites.map(c => <Box key={c.id} sx={{borderBottom: `1px solid ${tokens.line}`, pb: 1}}>
          <Typography fontWeight={600} fontSize={14.5}>{c.name} <Typography component="span" variant="caption" sx={{fontFamily: 'monospace'}}>{c.id}</Typography></Typography>
          <Typography variant="caption">{c.path}</Typography></Box>)}</Stack>
          : <Typography color="text.secondary" fontSize={14}>Nenhuma favorita. Clique na estrela de uma categoria no catálogo.</Typography>}
        <Button size="small" sx={{mt: 1.5}} onClick={load}>Atualizar lista</Button>
      </Card>
    </Box>}
    {tab === 'style' && <StyleSettings/>}
    <NicheDialog draft={draft} onClose={() => setDraft(null)} onSaved={t => { setDraft(null); setNotice(t); load(); }}/>
    {tab === 'niches' && <BulkBar count={sel.count} noun="nicho(s) selecionado(s)" onClear={sel.clear}>
      <Button size="small" variant="outlined" startIcon={<DeleteIcon/>} onClick={bulkDelete}>Excluir</Button>
    </BulkBar>}
    {confirm.dialog}
  </>;
}
