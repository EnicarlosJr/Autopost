import {useCallback, useEffect, useState} from 'react';
import {Box, Button, Card, Checkbox, Chip, Collapse, IconButton, InputAdornment, Stack, Switch, TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {GroupSchedule} from '../types/search';
import type {CampaignOptions, GroupSet, OfficialCategory} from '../types/campaign';
import CategoryTree, {OfficialChip} from '../components/CategoryTree';
import {Empty, Feedback, Loading} from '../components/Feedback';
import {PageHeader} from '../components/Ui';
import {BulkBar, ExpandAll, MultiPick, SelectAll, useConfirm, useSelection} from '../components/Bulk';
import {DeleteIcon, ExpandIcon, SearchIcon} from '../components/Icons';
import {display, tokens} from '../theme';

type Group = GroupSchedule & {categories: string[]; active: boolean; ml_categories?: OfficialCategory[]};

function GroupEditor({group, options, onSave, onRename, onRemove}: {group: Group; options: {name: string; count?: number}[];
  onSave: (g: Group) => Promise<void>; onRename: (newName: string) => Promise<void>; onRemove: () => void}) {
  const [value, setValue] = useState(group), [busy, setBusy] = useState(false), [name, setName] = useState(group.group_name);
  useEffect(() => { setValue(group); setName(group.group_name); }, [group]);
  const renamed = name.trim() && name.trim() !== group.group_name;
  // Limites de cada número: hora de 0 a 23 (fim até 24), contagens a partir de 1, dias a partir de 0.
  const LIMITS: Partial<Record<keyof Group, [number, number]>> = {start_hour: [0, 23], end_hour: [1, 24], max_per_day: [1, 500], gap_minutes: [1, 1440], repost_days: [0, 365]};
  const num = (key: keyof Group, label: string, width = 130) => { const [min, max] = LIMITS[key] ?? [0, 9999];
    return <TextField size="small" type="number" label={label} sx={{width}} value={value[key] as number} inputProps={{min, max}}
      onChange={e => setValue({...value, [key]: Math.min(max, Math.max(min, Math.round(Number(e.target.value) || 0)))})}/>; };
  const invalid = value.end_hour <= value.start_hour;
  return <Stack gap={2}>
    <Box>
      <Typography fontWeight={600} mb={.5}>Nome do grupo</Typography>
      <Stack direction={{xs: 'column', sm: 'row'}} gap={1} alignItems={{sm: 'flex-start'}}>
        <TextField size="small" label="Nome exato do grupo no WhatsApp" value={name} onChange={e => setName(e.target.value)} sx={{flex: 1}}
          helperText="Mudou o nome no WhatsApp? Troque aqui: publicações, buscas, conjuntos e campanhas em aberto passam a usar o nome novo."/>
        <Button variant="outlined" disabled={busy || !renamed} onClick={async () => { setBusy(true); try { await onRename(name.trim()); } finally { setBusy(false); } }}>
          Renomear</Button>
      </Stack>
    </Box>
    <Box>
      <Typography fontWeight={600} mb={.5}>Categorias oficiais que este grupo recebe</Typography>
      <Typography variant="body2" color="text.secondary" mb={1}>Usadas na distribuição "Por categoria" das campanhas, pela categoria do Mercado Livre de cada produto.</Typography>
      <CategoryTree selected={value.ml_categories || []} onChange={v => setValue({...value, ml_categories: v})} height={260}/>
    </Box>
    <MultiPick label="Categorias e tags antigas (opcional)" value={value.categories} options={options}
      onChange={v => setValue({...value, categories: v})} helper="Para produtos sem categoria oficial."/>
    <Stack direction="row" gap={1.5} flexWrap="wrap" useFlexGap>
      {num('start_hour', 'Das (hora)', 100)}{num('end_hour', 'Até (hora)', 100)}{num('max_per_day', 'Máximo por dia')}
      {num('gap_minutes', 'Intervalo (min)')}{num('repost_days', 'Repostar após (dias)', 160)}
    </Stack>
    {invalid && <Typography variant="body2" color="error.main">O horário final precisa ser depois do inicial.</Typography>}
    <Stack direction="row" gap={1} justifyContent="space-between" flexWrap="wrap">
      <Button variant="contained" disabled={busy || invalid} onClick={async () => { setBusy(true); try { await onSave(value); } finally { setBusy(false); } }}>Salvar grupo</Button>
      <Button color="error" startIcon={<DeleteIcon/>} onClick={onRemove}>Remover grupo</Button>
    </Stack>
  </Stack>;
}

export default function GroupsPage() {
  const [groups, setGroups] = useState<Group[]>([]), [options, setOptions] = useState<{name: string; count?: number}[]>([]);
  const [loading, setLoading] = useState(true), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [query, setQuery] = useState(''), [open, setOpen] = useState<string[]>([]), [newName, setNewName] = useState('');
  const sel = useSelection(); const confirm = useConfirm();
  const [sets, setSets] = useState<GroupSet[]>([]), [setName, setSetName] = useState('');
  const loadSets = useCallback(() => api.get<GroupSet[]>('/group-sets').then(r => setSets(r.data)).catch(() => {}), []);
  useEffect(() => { loadSets(); }, [loadSets]);
  const saveSet = async (name: string, groupsOf: string[], existing?: GroupSet) => {
    try {
      if (existing) await api.put(`/group-sets/${existing.id}`, {name, groups: groupsOf}); else await api.post('/group-sets', {name, groups: groupsOf});
      setNotice(`Conjunto "${name}" salvo com ${groupsOf.length} grupo(s).`); setSetName(''); loadSets();
    } catch (e) { setError(apiError(e, 'Não foi possível salvar o conjunto.')); }
  };
  const removeSet = async (s: GroupSet) => {
    if (!await confirm.ask('Excluir conjunto?', `O conjunto "${s.name}" sai da lista. Os grupos e as campanhas não mudam.`, 'Excluir')) return;
    await api.delete(`/group-sets/${s.id}`).catch(() => {}); loadSets();
  };
  const load = useCallback(async () => {
    try {
      const [g, o] = await Promise.all([api.get<Group[]>('/group-schedules'), api.get<CampaignOptions>('/campaigns/options')]);
      setGroups(g.data); setOptions([...o.data.categories, ...o.data.tags]); setError('');
    } catch (e) { setError(apiError(e, 'Não foi possível carregar os grupos.')); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const save = async (g: Group, text = `Grupo "${g.group_name}" salvo.`) => {
    try { await api.put(`/group-schedules/${encodeURIComponent(g.group_name)}`, g); setNotice(text); await load(); }
    catch (e) { setError(apiError(e, 'Não foi possível salvar o grupo.')); }
  };
  const shown = groups.filter(g => g.group_name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  const index = (name: string) => groups.findIndex(g => g.group_name === name);
  const picked = () => sel.ids.map(i => groups[i]).filter(Boolean);
  const bulkActive = async (active: boolean) => {
    const items = picked();
    try { for (const g of items) await api.put(`/group-schedules/${encodeURIComponent(g.group_name)}`, {...g, active}); }
    catch (e) { setError(apiError(e, 'Não foi possível alterar os grupos.')); return; }
    setNotice(`${items.length} grupo(s) ${active ? 'ativado(s)' : 'desativado(s)'}.`); sel.clear(); load();
  };
  const bulkRemove = async () => {
    const items = picked();
    if (!await confirm.ask(`Remover ${items.length} grupo(s)?`, 'Publicações que ainda iam sair para eles são canceladas. Eles saem também dos conjuntos e das campanhas em aberto. O histórico de enviadas fica.', 'Remover')) return;
    let done = 0;
    for (const g of items) if (await removeOne(g, false)) done++;
    if (done) setNotice(`${done} grupo(s) removido(s).`); sel.clear(); load(); loadSets();
  };
  /** Remove um grupo; se ainda houver publicações para sair, avisa e só cancela com a confirmação. */
  const removeOne = async (g: Group, ask = true): Promise<boolean> => {
    const name = g.group_name;
    let active = 0;
    try { active = (await api.get<{active: number}>(`/group-schedules/${encodeURIComponent(name)}/usage`)).data.active; } catch { /* segue sem a contagem */ }
    if (ask && !await confirm.ask(`Remover o grupo "${name}"?`,
      (active ? `${active} publicação(ões) ainda iam sair para ele e serão canceladas. ` : '')
      + 'Ele sai também dos conjuntos e das campanhas em aberto, e as buscas automáticas deixam de agendar para ele. O histórico de enviadas fica.',
      active ? `Cancelar ${active} e remover` : 'Remover')) return false;
    try { await api.delete(`/group-schedules/${encodeURIComponent(name)}`, {params: {cancel_pending: active > 0}}); return true; }
    catch (e) { setError(apiError(e, `Não foi possível remover "${name}".`)); return false; }
  };
  const rename = async (g: Group, newName: string) => {
    try {
      await api.post(`/group-schedules/${encodeURIComponent(g.group_name)}/rename`, {new_name: newName});
      setNotice(`Grupo renomeado para "${newName}".`); setOpen(o => o.map(x => x === g.group_name ? newName : x)); sel.clear(); await load(); loadSets();
    } catch (e) { setError(apiError(e, 'Não foi possível renomear o grupo.')); }
  };
  const add = async () => {
    const name = newName.trim(); if (!name) return;
    await save({group_name: name, categories: [], active: true, start_hour: 8, end_hour: 22, max_per_day: 12, gap_minutes: 40, repost_days: 7}, `Grupo "${name}" adicionado.`);
    setNewName('');
  };

  return <>
    <PageHeader title="Grupos" description="Os grupos do WhatsApp que recebem ofertas: categorias de interesse, horários e limites de cada um."/>
    <Card sx={{p: 2, mb: 3}}>
      <Stack direction={{xs: 'column', sm: 'row'}} gap={1.5}>
        <TextField size="small" label="Nome exato do grupo no WhatsApp" value={newName} onChange={e => setNewName(e.target.value)} onKeyDown={e => e.key === 'Enter' && add()} sx={{flex: 1}}/>
        <Button variant="contained" disabled={!newName.trim()} onClick={add}>Adicionar grupo</Button>
      </Stack>
    </Card>
    <Card sx={{p: 2, mb: 3}}>
      <Typography sx={{fontFamily: display, fontWeight: 700, fontSize: 16.5}} mb={.5}>Conjuntos de grupos</Typography>
      <Typography variant="body2" color="text.secondary" mb={1.5}>Um conjunto aplica vários grupos de uma vez numa campanha. Para criar, selecione os grupos na lista abaixo e use "Salvar como conjunto".</Typography>
      {!sets.length ? <Typography variant="body2">Nenhum conjunto ainda.</Typography> : <Stack gap={1}>{sets.map(s =>
        <Stack key={s.id} direction={{xs: 'column', sm: 'row'}} gap={1} alignItems={{sm: 'center'}} sx={{p: 1.25, border: `1px solid ${tokens.line}`, borderRadius: 2}}>
          <Box flex={1} minWidth={0}>
            <Typography fontWeight={650}>{s.name}</Typography>
            <Stack direction="row" gap={.5} flexWrap="wrap" mt={.25}>{s.groups.map(g => <Chip key={g} size="small" label={g}/>)}</Stack>
          </Box>
          <Stack direction="row" gap={.5}>
            <Tooltip title="Troca os grupos do conjunto pelos selecionados na lista"><span>
              <Button size="small" disabled={!sel.count} onClick={() => saveSet(s.name, picked().map(g => g.group_name), s)}>Usar seleção</Button></span></Tooltip>
            <IconButton size="small" aria-label={`Excluir conjunto ${s.name}`} onClick={() => removeSet(s)}><DeleteIcon fontSize="small"/></IconButton>
          </Stack>
        </Stack>)}</Stack>}
    </Card>
    <Stack direction={{xs: 'column', md: 'row'}} gap={1} alignItems={{md: 'center'}} justifyContent="space-between" mb={1.5}>
      <SelectAll total={shown.length} selected={shown.filter(g => sel.has(index(g.group_name))).length}
        onAll={() => sel.setAll(shown.map(g => index(g.group_name)))} onNone={sel.clear}/>
      <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
        <TextField size="small" placeholder="Buscar grupo" value={query} onChange={e => setQuery(e.target.value)}
          InputProps={{startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small"/></InputAdornment>}}/>
        {shown.length > 1 && <ExpandAll onExpand={() => setOpen(shown.map(g => g.group_name))} onCollapse={() => setOpen([])}/>}
      </Stack>
    </Stack>
    <Feedback error={error} notice={notice} onRetry={load} onClose={() => { setError(''); setNotice(''); }}/>
    <Loading show={loading}/>
    {!loading && !shown.length && <Empty text={groups.length ? 'Nenhum grupo com esse nome.' : 'Nenhum grupo ainda. Adicione pelo nome exato que aparece no WhatsApp.'}/>}
    <Stack gap={1}>
      {shown.map(g => { const i = index(g.group_name); const expanded = open.includes(g.group_name);
        return <Card key={g.group_name} sx={{opacity: g.active ? 1 : .65}}>
          <Stack direction="row" alignItems="center" gap={1} sx={{px: 1, py: 1}}>
            <Checkbox checked={sel.has(i)} onChange={() => sel.toggle(i)} inputProps={{'aria-label': `Selecionar ${g.group_name}`}}/>
            <Box flex={1} minWidth={0} sx={{cursor: 'pointer'}} onClick={() => setOpen(o => expanded ? o.filter(x => x !== g.group_name) : [...o, g.group_name])}>
              <Typography sx={{fontFamily: display, fontWeight: 700, fontSize: 16.5}} noWrap>{g.group_name}</Typography>
              <Stack direction="row" gap={.5} flexWrap="wrap" mt={.25}>
                {(g.ml_categories || []).map(c => <OfficialChip key={c.id} cat={c}/>)}
                {g.categories.map(c => <Chip key={c} size="small" variant="outlined" label={c}/>)}
                {!g.categories.length && !g.ml_categories?.length && <Typography variant="caption">Sem categorias</Typography>}
                <Typography variant="caption" sx={{ml: 1}}>{g.start_hour}h às {g.end_hour}h, até {g.max_per_day} por dia</Typography>
              </Stack>
            </Box>
            <Tooltip title={g.active ? 'Ativo: aparece nas campanhas' : 'Inativo: não recebe campanhas'}>
              <Switch checked={g.active} onChange={e => save({...g, active: e.target.checked}, e.target.checked ? 'Grupo ativado.' : 'Grupo desativado.')} inputProps={{'aria-label': 'Grupo ativo'}}/>
            </Tooltip>
            <Tooltip title="Remover grupo"><IconButton aria-label={`Remover ${g.group_name}`}
              onClick={async () => { if (await removeOne(g)) { setNotice(`Grupo "${g.group_name}" removido.`); sel.clear(); load(); loadSets(); } }}>
              <DeleteIcon fontSize="small"/></IconButton></Tooltip>
            <IconButton aria-label={expanded ? 'Recolher' : 'Editar'} aria-expanded={expanded}
              onClick={() => setOpen(o => expanded ? o.filter(x => x !== g.group_name) : [...o, g.group_name])}
              sx={{transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform .15s'}}><ExpandIcon/></IconButton>
          </Stack>
          <Collapse in={expanded} unmountOnExit>
            <Box sx={{px: 2, pb: 2, pt: 1.5, borderTop: `1px solid ${tokens.line}`}}>
              <GroupEditor group={g} options={options} onSave={v => save(v)} onRename={n => rename(g, n)}
                onRemove={async () => { if (await removeOne(g)) { setNotice(`Grupo "${g.group_name}" removido.`); sel.clear(); load(); loadSets(); } }}/>
            </Box>
          </Collapse>
        </Card>; })}
    </Stack>
    <BulkBar count={sel.count} noun="grupo(s) selecionado(s)" onClear={sel.clear}>
      <TextField size="small" placeholder="Nome do conjunto" value={setName} onChange={e => setSetName(e.target.value)} sx={{width: 170}}
        onKeyDown={e => { if (e.key === 'Enter' && setName.trim()) saveSet(setName.trim(), picked().map(g => g.group_name), sets.find(s => s.name.toLocaleLowerCase() === setName.trim().toLocaleLowerCase())); }}/>
      <Button size="small" variant="contained" disabled={!setName.trim()}
        onClick={() => saveSet(setName.trim(), picked().map(g => g.group_name), sets.find(s => s.name.toLocaleLowerCase() === setName.trim().toLocaleLowerCase()))}>Salvar como conjunto</Button>
      <Button size="small" variant="outlined" onClick={() => bulkActive(true)}>Ativar</Button>
      <Button size="small" variant="outlined" onClick={() => bulkActive(false)}>Desativar</Button>
      <Button size="small" variant="outlined" startIcon={<DeleteIcon/>} onClick={bulkRemove}>Remover</Button>
    </BulkBar>
    {confirm.dialog}
  </>;
}
