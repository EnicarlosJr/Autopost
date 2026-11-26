import {Fragment, useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {Link, useLocation, useNavigate, useParams, useSearchParams} from 'react-router-dom';
import {Alert, Autocomplete, Box, Button, Card, Checkbox, Chip, Collapse, FormControlLabel, InputAdornment, MenuItem, Radio, RadioGroup, Stack, Step,
  StepButton, Stepper, Switch, TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography, useMediaQuery} from '@mui/material';
import {api, apiError} from '../services/api';
import type {Niche} from '../types/catalog';
import CampaignSearchPanel from '../components/CampaignSearchPanel';
import ProductPickerDialog from '../components/ProductPickerDialog';
import CategoryTree, {OfficialChip} from '../components/CategoryTree';
import {PriceTag} from '../components/Ui';
import type {Campaign, CampaignConfig, CampaignOptions, CampaignPlan, CampaignProductRow, GroupSet, GroupTarget, OfficialCategory} from '../types/campaign';
import {dateTime, duration, rhythm, strategyLabel, WEEKDAYS} from '../campaignLabels';
import {MultiPick, SelectAll} from '../components/Bulk';
import {SendModeFields} from '../components/Fields';
import TemplateEditor from '../components/TemplateEditor';
import type {Settings} from '../types/models';
import {PageHeader} from '../components/Ui';
import {SearchIcon} from '../components/Icons';
import {display, tokens} from '../theme';

const STEPS = ['Informações', 'Nichos e categorias', 'Busca de produtos', 'Seleção dos produtos', 'Grupos de destino', 'Regras de automação', 'Revisão'];
const EMPTY: CampaignConfig = {name: '', niche_ids: [], ml_categories: [], include_keywords: [], exclude_keywords: [], product_ids: [], categories: [], exclude_categories: [], tags: [], tag_mode: 'any', exclude_tags: [],
  include_uncategorized: false, min_discount: 0, groups: [], strategy: 'balanced', total_limit: 20, block_size: 1, interval_minutes: 5,
  interval_max_minutes: 0, start_at: null, start_hour: 8, end_hour: 22, weekdays: [0, 1, 2, 3, 4, 5, 6], daily_limit: 0, pause_every: 0, pause_minutes: 0,
  end_at: null, message_gap_seconds: 20, reuse_days: null, group_daily_limit: 0,
  send_mode: 'preview', watermark_text: '', watermark_handle: '', custom_style: false, message_template: ''};
const PRESETS: [string, Partial<CampaignConfig>][] = [
  ['1 a cada 2 min', {block_size: 1, interval_minutes: 2, interval_max_minutes: 0}],
  ['1 a cada 5 min', {block_size: 1, interval_minutes: 5, interval_max_minutes: 0}],
  ['3 a cada 10 min', {block_size: 3, interval_minutes: 10, interval_max_minutes: 0}],
];
const toLocal = (iso: string | null) => { if (!iso) return ''; const d = new Date(iso); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };
const int = (v: string, min = 0) => Math.max(min, Math.floor(Number(v) || 0));

function Summary({plan, loading, config, productCount, onRespectLimit}: {plan: CampaignPlan | null; loading: boolean; config: CampaignConfig;
  /** Produtos adicionados à campanha; null = campanha antiga, que usa filtros. */
  productCount: number | null; onRespectLimit: (limit: number) => void}) {
  const stat = (value: number | string, label: string) => <Box>
    <Typography sx={{fontFamily: display, fontWeight: 750, fontSize: 26, lineHeight: 1.1}}>{value}</Typography>
    <Typography variant="body2" color="text.secondary">{label}</Typography></Box>;
  return <Card sx={{p: 2.5, position: {md: 'sticky'}, top: 24, opacity: loading ? .6 : 1, transition: 'opacity .15s'}} aria-live="polite">
    <Typography fontWeight={650} mb={1.5}>Resumo da campanha</Typography>
    {!plan ? <Typography color="text.secondary" fontSize={14}>Calculando…</Typography> : <>
      <Box sx={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 2, mb: 2}}>
        {stat(productCount ?? plan.matching, 'produtos na campanha')}{stat(plan.messages, 'anúncios programados')}
        {stat(plan.selected, 'produtos usados')}{stat(plan.duration_minutes ? duration(plan.duration_minutes) : '0 min', 'duração prevista')}
      </Box>
      {plan.start && <Typography fontSize={14}>Início {dateTime(plan.start)}, término {dateTime(plan.end)}.</Typography>}
      <Typography fontSize={14} color="text.secondary">{rhythm(config)}, das {config.start_hour}h às {config.end_hour}h.</Typography>
      {plan.per_group.length > 0 && <Stack gap={.5} mt={1.5}>{plan.per_group.map(g =>
        <Stack key={g.group} direction="row" justifyContent="space-between" fontSize={14}><Box sx={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', mr: 1}}>{g.group}</Box><b>{g.count}</b></Stack>)}</Stack>}
      {plan.errors.map(e => <Alert key={e} severity="error" sx={{mt: 1.5}}>{e}</Alert>)}
      {plan.warnings.map(w => <Alert key={w} severity="warning" sx={{mt: 1.5}}>{w}</Alert>)}
      {(plan.group_limits?.length ?? 0) > 0 && <Button size="small" variant="outlined" sx={{mt: 1}}
        onClick={() => onRespectLimit(Math.min(...plan.group_limits!.map(g => g.limit)))}>
        Respeitar o limite do grupo ({Math.min(...plan.group_limits!.map(g => g.limit))} por dia)</Button>}
    </>}
  </Card>;
}

export default function CampaignEditor() {
  const {id} = useParams(); const [params] = useSearchParams(); const navigate = useNavigate();
  const desktop = useMediaQuery('(min-width:960px)');
  const [step, setStep] = useState(Number(params.get('step') || 0));
  const [config, setConfig] = useState<CampaignConfig>(EMPTY);
  const [status, setStatus] = useState('draft'), [loaded, setLoaded] = useState(!id);
  const [options, setOptions] = useState<CampaignOptions>({categories: [], tags: [], uncategorized: 0, groups: []});
  const [plan, setPlan] = useState<CampaignPlan | null>(null), [planning, setPlanning] = useState(false);
  const [error, setError] = useState(''), [saving, setSaving] = useState(false);
  const location = useLocation();
  const [notice, setNotice] = useState<string>((location.state as {notice?: string} | null)?.notice ?? '');
  const [groupQuery, setGroupQuery] = useState(''), [newGroup, setNewGroup] = useState(''), [advanced, setAdvanced] = useState(false);
  const [campaignId, setCampaignId] = useState<number | null>(id ? Number(id) : null);
  const [picking, setPicking] = useState(false);
  const [niches, setNiches] = useState<Niche[]>([]), [products, setProducts] = useState<CampaignProductRow[]>([]), [removing, setRemoving] = useState<number[]>([]);
  const [legacy, setLegacy] = useState(false);
  const [sets, setSets] = useState<GroupSet[]>([]), [setName, setSetName] = useState('');
  const [profile, setProfile] = useState<Settings | null>(null);   // padrão do perfil (mensagem e foto)
  useEffect(() => {
    api.get<Settings>('/automations/settings').then(r => {
      setProfile(r.data);
      if (!id) setConfig(c => ({...c, send_mode: r.data.send_mode || c.send_mode}));   // campanha nova começa com a forma de envio do perfil
    }).catch(() => {});
  }, [id]);
  const loadSets = useCallback(() => api.get<GroupSet[]>('/group-sets').then(r => setSets(r.data)).catch(() => {}), []);
  useEffect(() => { loadSets(); }, [loadSets]);
  const pendingProducts = useRef((params.get('products') || '').split(',').map(Number).filter(Boolean));
  const set = (patch: Partial<CampaignConfig>) => setConfig(c => ({...c, ...patch}));

  const loadProducts = useCallback(async (cid: number) => {
    try { setProducts((await api.get<CampaignProductRow[]>(`/campaigns/${cid}/products`)).data); } catch { /* lista opcional */ }
  }, []);
  useEffect(() => { api.get<Niche[]>('/niches').then(r => setNiches(r.data)).catch(() => {}); }, []);
  useEffect(() => { if (campaignId) loadProducts(campaignId); }, [campaignId, loadProducts]);
  const loadOptions = useCallback(() => api.get<CampaignOptions>('/campaigns/options').then(r => setOptions(r.data))
    .catch(e => setError(apiError(e, 'Não foi possível carregar categorias e grupos.'))), []);
  useEffect(() => { loadOptions(); }, [loadOptions]);
  /** Liga um grupo desativado em Grupos sem sair da campanha, e já o marca nela. */
  const activateGroup = async (name: string) => {
    try {
      const all = (await api.get<Record<string, unknown>[]>('/group-schedules')).data;
      const current = all.find(g => g.group_name === name);
      if (!current) throw new Error('Grupo não encontrado em Grupos.');
      await api.put(`/group-schedules/${encodeURIComponent(name)}`, {...current, active: true});
      await loadOptions();
      if (!selected.has(name)) set({groups: [...config.groups, {group: name, limit: 0, categories: []}]});
    } catch (e) { setError(apiError(e, 'Não foi possível ativar o grupo.')); }
  };
  useEffect(() => {
    if (!id) return;
    api.get<Campaign>(`/campaigns/${id}`).then(r => {
      const {id: _id, status: st, display_status, created_at, confirmed_at, counts, total, sent, failed, pending, progress, next_send, products_count, searches_count, niche_names, ...cfg} = r.data; // eslint-disable-line @typescript-eslint/no-unused-vars
      setConfig({...EMPTY, ...cfg}); setStatus(st); setLoaded(true);
      setLegacy(Boolean(cfg.categories?.length || cfg.tags?.length || cfg.product_ids?.length));
      if (cfg.pause_every || cfg.daily_limit || cfg.interval_max_minutes) setAdvanced(true);
    }).catch(e => setError(apiError(e, 'Campanha não encontrada.')));
  }, [id]);

  // Prévia ao vivo (sem gravar), meio segundo depois da última mudança.
  const seq = useRef(0);
  useEffect(() => {
    if (!loaded) return;
    const mine = ++seq.current; setPlanning(true);
    const t = setTimeout(async () => {
      try {
        const r = await api.post<CampaignPlan>('/campaigns/preview', {...config, name: config.name || 'Rascunho'}, {params: campaignId ? {campaign_id: campaignId} : {}});
        if (mine === seq.current) setPlan(r.data);
      } catch (e) { if (mine === seq.current) setError(apiError(e, 'Não foi possível calcular a prévia.')); }
      finally { if (mine === seq.current) setPlanning(false); }
    }, 500);
    return () => clearTimeout(t);
  }, [config, loaded, campaignId, products.length]);

  const selected = new Set(config.groups.map(g => g.group));
  const allGroups = useMemo(() => {
    const names = new Map(options.groups.map(g => [g.name, g]));
    config.groups.forEach(g => { if (!names.has(g.group)) names.set(g.group, {name: g.group, active: true, categories: []}); });
    return [...names.values()];
  }, [options.groups, config.groups]);
  const visibleGroups = allGroups.filter(g => g.name.toLocaleLowerCase().includes(groupQuery.toLocaleLowerCase()));
  const toggleGroup = (name: string) => set({groups: selected.has(name) ? config.groups.filter(g => g.group !== name)
    : [...config.groups, {group: name, limit: 0, categories: []}]});
  const patchGroup = (name: string, patch: Partial<GroupTarget>) => set({groups: config.groups.map(g => g.group === name ? {...g, ...patch} : g)});
  const addGroup = () => { const name = newGroup.trim(); if (name && !selected.has(name)) set({groups: [...config.groups, {group: name, limit: 0, categories: []}]}); setNewGroup(''); };
  const categoryNames = [...options.categories, ...options.tags];

  const noProducts = !products.length && !legacy;
  const stepErrors = [
    !config.name.trim() ? 'Dê um nome à campanha.' : '',
    noProducts ? 'Adicione produtos à campanha pela busca ou pela tela Produtos.' : '',
    !config.groups.length ? 'Selecione pelo menos um grupo.' : '',
    plan?.errors[0] || '',
    plan && !plan.messages ? 'Nenhum anúncio seria programado com esta configuração.' : '',
  ];
  /** Garante que a campanha existe (rascunho) antes de buscar ou adicionar produtos. */
  const ensureSaved = async (): Promise<number | null> => {
    if (!config.name.trim()) { setError('Dê um nome à campanha antes de buscar produtos.'); setStep(0); return null; }
    try {
      const body = {...config, name: config.name.trim()};
      const saved = campaignId ? (await api.put<Campaign>(`/campaigns/${campaignId}`, body)).data : (await api.post<Campaign>('/campaigns', body)).data;
      if (!campaignId) {
        setCampaignId(saved.id);
        if (pendingProducts.current.length) { await api.post(`/campaigns/${saved.id}/products`, {product_ids: pendingProducts.current}); pendingProducts.current = []; }
        window.history.replaceState(null, '', `/campaigns/${saved.id}/edit`);
      }
      loadProducts(saved.id);
      return saved.id;
    } catch (e) { setError(apiError(e, 'Não foi possível salvar o rascunho.')); return null; }
  };
  const goTo = async (next: number) => {
    if (next >= 2 && !campaignId && !await ensureSaved()) return;
    setStep(next);
  };
  const applyNiches = async (ids: number[]) => {
    try {
      const r = await api.get(`/campaigns/${campaignId ?? 0}/niche-defaults`, {params: {niche_ids: ids.join(',')}});
      // As palavras-chave ficam no nicho: a busca por nicho usa as de cada um (até 10 por busca).
      // Copiar todas para a campanha misturava os nichos e passava do limite com vários nichos juntos.
      const merged = new Map(config.ml_categories.map(c => [c.id, c])); (r.data.categories as OfficialCategory[]).forEach(c => merged.set(c.id, c));
      set({niche_ids: ids, ml_categories: [...merged.values()]});
    } catch (e) { setError(apiError(e, 'Não foi possível aplicar o nicho.')); }
  };
  const removeProducts = async (ids: number[]) => {
    if (!campaignId) return;
    try { await api.post(`/campaigns/${campaignId}/products/remove`, {product_ids: ids}); setRemoving([]); loadProducts(campaignId); }
    catch (e) { setError(apiError(e, 'Não foi possível remover.')); }
  };
  const save = async (schedule: boolean) => {
    setSaving(true); setError('');
    try {
      const body = {...config, name: config.name.trim()};
      const saved = campaignId ? (await api.put<Campaign>(`/campaigns/${campaignId}`, body)).data : (await api.post<Campaign>('/campaigns', body)).data;
      if (!campaignId && pendingProducts.current.length) await api.post(`/campaigns/${saved.id}/products`, {product_ids: pendingProducts.current});
      if (schedule) await api.post(`/campaigns/${saved.id}/${status === 'paused' ? 'resume' : 'confirm'}`);
      navigate('/campaigns', {replace: true});
    } catch (e) { setError(apiError(e, 'Não foi possível salvar a campanha.')); }
    finally { setSaving(false); }
  };

  const productsStep = <Stack gap={2.5}>
    {config.product_ids.length > 0 ? <Alert severity="info" action={<Button color="inherit" size="small" onClick={() => set({product_ids: []})}>Usar filtros</Button>}>
      {config.product_ids.length} produto(s) escolhidos na tela Produtos. Os filtros abaixo não se aplicam.</Alert> : <>
      <MultiPick label="Categorias" value={config.categories} onChange={v => set({categories: v})} options={options.categories} free={false}
        helper="Vazio = todas as categorias. Os achados aprovados recebem o nome da busca como categoria."/>
      <MultiPick label="Excluir categorias" value={config.exclude_categories} onChange={v => set({exclude_categories: v})} options={options.categories} free={false}/>
      <Box>
        <MultiPick label="Tags" value={config.tags} onChange={v => set({tags: v})} options={options.tags} free={false}/>
        {config.tags.length > 1 && <RadioGroup row value={config.tag_mode} onChange={e => set({tag_mode: e.target.value as 'any' | 'all'})}>
          <FormControlLabel value="any" control={<Radio size="small"/>} label="Qualquer uma das tags"/>
          <FormControlLabel value="all" control={<Radio size="small"/>} label="Todas as tags"/>
        </RadioGroup>}
      </Box>
      <MultiPick label="Excluir tags" value={config.exclude_tags} onChange={v => set({exclude_tags: v})} options={options.tags} free={false}/>
      <Stack direction={{xs: 'column', sm: 'row'}} gap={2} alignItems={{sm: 'center'}}>
        <TextField label="Desconto mínimo" type="number" value={config.min_discount} sx={{width: 180}}
          onChange={e => set({min_discount: Math.min(95, int(e.target.value))})} InputProps={{endAdornment: <InputAdornment position="end">%</InputAdornment>}}/>
        <FormControlLabel control={<Switch checked={config.include_uncategorized} onChange={e => set({include_uncategorized: e.target.checked})}/>}
          label={`Incluir produtos sem categoria (${options.uncategorized})`}/>
      </Stack>
    </>}
  </Stack>;

  const infoStep = <Stack gap={2}>
    <TextField label="Nome da campanha" value={config.name} onChange={e => set({name: e.target.value})} placeholder="Floripa Teste" autoFocus/>
    <Typography variant="body2" color="text.secondary">Cada campanha tem seus próprios produtos, categorias, grupos e regras. Nada é enviado até a confirmação na revisão.</Typography>
  </Stack>;

  const nicheStep = <Stack gap={2.5}>
    <Box>
      <Typography fontWeight={600} mb={.5}>Nichos salvos no seu perfil</Typography>
      <Typography variant="body2" color="text.secondary" mb={1.5}>Marque os nichos desta campanha. Na próxima etapa, cada nicho vira uma busca com as próprias palavras,
        categorias e público. Mudanças aqui não alteram o nicho salvo.</Typography>
      {niches.length ? <Stack direction="row" gap={.75} flexWrap="wrap">{niches.map(n => { const on = config.niche_ids.includes(n.id);
        return <Chip key={n.id} label={`${n.favorite ? '★ ' : ''}${n.name}`} color={on ? 'primary' : 'default'} variant={on ? 'filled' : 'outlined'}
          onClick={() => on ? set({niche_ids: config.niche_ids.filter(x => x !== n.id)}) : applyNiches([...config.niche_ids, n.id])}/>; })}</Stack>
        : <Typography variant="body2" color="text.secondary">Nenhum nicho salvo. Crie em <Link to="/profile">Meu perfil</Link> ou escolha as categorias abaixo.</Typography>}
    </Box>
    <Box>
      <Typography fontWeight={600} mb={1}>Categorias oficiais da campanha</Typography>
      <CategoryTree selected={config.ml_categories} onChange={v => set({ml_categories: v})} height={320}/>
    </Box>
    <MultiPick label="Palavras-chave da campanha" value={config.include_keywords} onChange={v => set({include_keywords: v})} options={[]}
      helper="Sugeridas como palavras de busca na próxima etapa."/>
    <MultiPick label="Palavras excluídas" value={config.exclude_keywords} onChange={v => set({exclude_keywords: v})} options={[]}/>
  </Stack>;

  const searchStep = campaignId ? <CampaignSearchPanel campaignId={campaignId} onAdded={() => loadProducts(campaignId)}
    niches={niches} chosenNiches={config.niche_ids} onChooseNiches={ids => set({niche_ids: ids})}
    defaults={{niche_id: config.niche_ids[0] ?? null, niche_name: niches.find(n => n.id === config.niche_ids[0])?.name ?? '',
      categories: config.ml_categories, keywords: config.include_keywords, exclude_keywords: config.exclude_keywords,
      gender: niches.find(n => config.niche_ids.includes(n.id) && n.gender && n.gender !== 'any')?.gender ?? 'any'}}/>
    : <Typography color="text.secondary">Salvando o rascunho…</Typography>;

  const selectionStep = <Stack gap={2}>
    <Stack direction={{xs: 'column', sm: 'row'}} justifyContent="space-between" gap={1} alignItems={{sm: 'center'}}>
      <Typography>{products.length} produto(s) nesta campanha.</Typography>
      <Stack direction="row" gap={1}>
        <Button onClick={() => goTo(2)}>Fazer outra busca</Button>
        <Button variant="outlined" disabled={!campaignId} onClick={() => setPicking(true)}>Escolher dos meus produtos</Button>
      </Stack>
    </Stack>
    {products.length > 0 && <Stack direction="row" gap={1} alignItems="center">
      <SelectAll total={products.length} selected={removing.length} onAll={() => setRemoving(products.map(p => p.product_id))} onNone={() => setRemoving([])}/>
      <Button color="error" disabled={!removing.length} onClick={() => removeProducts(removing)}>Remover {removing.length || ''} da campanha</Button>
    </Stack>}
    {!products.length ? <Alert severity="info">Nenhum produto ainda. Use a etapa Busca de produtos ou "Escolher dos meus produtos" para pegar os que você já tem cadastrados.</Alert>
      : <Card variant="outlined" sx={{maxHeight: 480, overflow: 'auto'}}>{products.map(p =>
        <Stack key={p.product_id} direction="row" gap={1.5} alignItems="center" sx={{p: 1.25, borderBottom: `1px solid ${tokens.line}`}}>
          <Checkbox checked={removing.includes(p.product_id)} onChange={() => setRemoving(r => r.includes(p.product_id) ? r.filter(x => x !== p.product_id) : [...r, p.product_id])}
            inputProps={{'aria-label': `Selecionar ${p.title}`}} sx={{p: .5}}/>
          <Box component="img" src={p.image_url} alt="" sx={{width: 52, height: 52, objectFit: 'contain', borderRadius: 1.5, bgcolor: '#fff', flexShrink: 0, border: `1px solid ${tokens.line}`}}/>
          <Box flex={1} minWidth={0}>
            <Typography fontSize={14.5} fontWeight={600} noWrap title={p.title}>{p.title}</Typography>
            <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap" mt={.25}>
              <PriceTag price={p.price} original={p.original_price} size="sm"/>
              {p.ml_category_id && <OfficialChip cat={{id: p.ml_category_id, include_children: false, name: p.category_name || p.ml_category_id, path: p.category_path, is_leaf: true}}/>}
              {!p.ready && <Chip size="small" color="warning" label="Sem preço lido"/>}
            </Stack>
          </Box>
        </Stack>)}</Card>}
    {legacy && <Card variant="outlined" sx={{p: 2}}>
      <Typography fontWeight={600} mb={.5}>Filtros antigos</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>Esta campanha foi criada antes da busca por campanha. {products.length
        ? 'Como ela já tem produtos adicionados, estes filtros são ignorados.' : 'Enquanto não houver produtos adicionados, ela usa estes filtros.'}</Typography>
      {productsStep}
    </Card>}
  </Stack>;

  const applySet = (s: GroupSet) => {
    const have = new Set(config.groups.map(g => g.group));
    set({groups: [...config.groups, ...s.groups.filter(g => !have.has(g)).map(g => ({group: g, limit: 0, categories: []}))]});
  };
  const saveSet = async () => {
    const name = setName.trim(); if (!name || !config.groups.length) return;
    try {
      const old = sets.find(s => s.name.toLocaleLowerCase() === name.toLocaleLowerCase());
      const body = {name, groups: config.groups.map(g => g.group)};
      if (old) await api.put(`/group-sets/${old.id}`, body); else await api.post('/group-sets', body);
      setSetName(''); loadSets();
    } catch (e) { setError(apiError(e, 'Não foi possível salvar o conjunto.')); }
  };
  const groupsStep = <Stack gap={2.5}>
    <Box>
      <Typography fontWeight={600} mb={.5}>Conjuntos de grupos</Typography>
      {sets.length ? <Stack direction="row" gap={.75} flexWrap="wrap" mb={1}>{sets.map(s =>
        <Tooltip key={s.id} title={s.groups.join(', ')}><Chip label={`${s.name} (${s.groups.length})`} variant="outlined" onClick={() => applySet(s)}/></Tooltip>)}</Stack>
        : <Typography variant="body2" color="text.secondary" mb={1}>Nenhum conjunto salvo. Selecione os grupos abaixo e salve como conjunto para reaproveitar.</Typography>}
      <Stack direction="row" gap={1}>
        <TextField size="small" label="Salvar seleção como conjunto" placeholder="Floripa" value={setName} onChange={e => setSetName(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && saveSet()} sx={{flex: 1, maxWidth: 360}}/>
        <Button onClick={saveSet} disabled={!setName.trim() || !config.groups.length}>Salvar conjunto</Button>
      </Stack>
    </Box>
    <TextField select label="Estratégia de distribuição" value={config.strategy} onChange={e => set({strategy: e.target.value as CampaignConfig['strategy']})}
      helperText={strategyLabel[config.strategy][1]}>
      {Object.entries(strategyLabel).map(([k, [label]]) => <MenuItem key={k} value={k}>{label}</MenuItem>)}
    </TextField>
    <TextField label="Total de anúncios da campanha" type="number" value={config.total_limit} sx={{maxWidth: 260}}
      onChange={e => set({total_limit: Math.min(500, int(e.target.value, 1))})} helperText="Soma de todas as mensagens, em todos os grupos."/>
    <Box>
      <Stack direction={{xs: 'column', sm: 'row'}} gap={1} alignItems={{sm: 'center'}} justifyContent="space-between" mb={1}>
        <SelectAll total={visibleGroups.length} selected={visibleGroups.filter(g => selected.has(g.name)).length}
          onAll={() => set({groups: [...config.groups, ...visibleGroups.filter(g => !selected.has(g.name) && g.active).map(g => ({group: g.name, limit: 0, categories: []}))]})}
          onNone={() => set({groups: config.groups.filter(g => !visibleGroups.some(v => v.name === g.group))})} label="Selecionar todos"/>
        <TextField size="small" placeholder="Buscar grupo" value={groupQuery} onChange={e => setGroupQuery(e.target.value)}
          InputProps={{startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small"/></InputAdornment>}}/>
      </Stack>
      <Typography variant="body2" color="text.secondary" mb={1}>{config.groups.length} de {allGroups.length} grupo(s) selecionado(s).
        {config.strategy === 'balanced' && ' Limite vazio divide o total igualmente entre os grupos.'}</Typography>
      <Card sx={{maxHeight: 420, overflow: 'auto'}}>
        {!visibleGroups.length && <Typography p={2} color="text.secondary">Nenhum grupo encontrado. Adicione pelo nome exato abaixo.</Typography>}
        {visibleGroups.map(g => { const target = config.groups.find(t => t.group === g.name); const on = Boolean(target);
          return <Box key={g.name} sx={{px: 1.5, py: 1, borderBottom: `1px solid ${tokens.line}`, '&:last-child': {borderBottom: 0}, opacity: g.active ? 1 : .55}}>
            <Stack direction={{xs: 'column', sm: 'row'}} gap={1} alignItems={{sm: 'center'}}>
              <FormControlLabel sx={{flex: 1, minWidth: 0, mr: 0}} control={<Checkbox checked={on} disabled={!g.active && !on} onChange={() => toggleGroup(g.name)}/>}
                label={<Box><Typography fontWeight={600} fontSize={14.5}>{g.name}{!g.active && ' (inativo)'}</Typography>
                  {config.strategy === 'category' && <Typography variant="caption">{[...(g.ml_categories || []).map(c => c.name || c.id), ...g.categories].join(', ') || 'Sem categorias no cadastro do grupo'}</Typography>}</Box>}/>
              {!g.active && <Tooltip title="Desligado em Grupos. Ativar faz o grupo voltar a receber campanhas.">
                <Button size="small" variant="outlined" onClick={() => activateGroup(g.name)}>Ativar e usar</Button></Tooltip>}
              {on && <TextField size="small" type="number" label="Limite" value={target!.limit || ''} placeholder="Auto" sx={{width: 110}}
                onChange={e => patchGroup(g.name, {limit: int(e.target.value)})}/>}
            </Stack>
            {on && config.strategy === 'custom' && <Box mt={1} ml={{sm: 4}}>
              {config.ml_categories.length > 0 && <Autocomplete multiple size="small" options={config.ml_categories} sx={{mb: 1}}
                value={config.ml_categories.filter(c => target!.ml_categories?.some(x => x.id === c.id))}
                getOptionLabel={c => c.name || c.id} isOptionEqualToValue={(a, b) => a.id === b.id}
                onChange={(_, v) => patchGroup(g.name, {ml_categories: v})}
                renderInput={p => <TextField {...p} label="Categorias oficiais que este grupo recebe"/>}/>}
              <MultiPick size="small" label="Categorias ou tags que este grupo recebe" value={target!.categories} options={categoryNames}
                onChange={v => patchGroup(g.name, {categories: v})}/></Box>}
          </Box>; })}
      </Card>
      <Stack direction="row" gap={1} mt={1.5}>
        <TextField size="small" label="Adicionar grupo pelo nome exato" value={newGroup} onChange={e => setNewGroup(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addGroup()} sx={{flex: 1}}/>
        <Button onClick={addGroup} disabled={!newGroup.trim()}>Adicionar</Button>
      </Stack>
      {config.strategy === 'category' && <Typography variant="body2" color="text.secondary" mt={1}>As categorias de cada grupo ficam em <Link to="/groups">Grupos</Link>.</Typography>}
    </Box>
  </Stack>;

  /** Personalizar: começa com o que está no perfil, para editar a partir dele. */
  const toggleCustom = (custom: boolean) => set(custom ? {custom_style: true,
    message_template: config.message_template || profile?.message_template || profile?.default_template || '',
    watermark_text: config.watermark_text || profile?.watermark_text || '', watermark_handle: config.watermark_handle || profile?.watermark_handle || ''}
    : {custom_style: false});
  const sendModeBox = <Box>
    <Typography fontWeight={600} mb={.5}>Mensagem e foto</Typography>
    <FormControlLabel control={<Switch checked={!config.custom_style} onChange={e => toggleCustom(!e.target.checked)}/>}
      label="Usar o padrão do perfil (modelo da mensagem e marca d'água)"/>
    <Typography variant="body2" color="text.secondary" mb={2}>
      {config.custom_style ? 'Esta campanha usa a própria mensagem e a própria marca d\'água. ' : <>O padrão fica em <Link to="/profile?tab=style">Meu perfil, aba Mensagem e foto</Link>. </>}
      A identificação de publicidade ({profile?.disclosure_text || '#publi'}) vai sempre, na mensagem e na foto.</Typography>
    <Typography fontWeight={600} fontSize={14} mb={1}>Forma de envio</Typography>
    <SendModeFields mode={config.send_mode} onChange={set} fixed={!config.custom_style}
      text={config.custom_style ? config.watermark_text : profile?.watermark_text || ''}
      handle={config.custom_style ? config.watermark_handle : profile?.watermark_handle || ''}
      sampleUrl={campaignId && products.length ? `/campaigns/${campaignId}/sample-image` : null} refreshKey={products.length}
      sampleNote="Prévia com o primeiro produto da campanha." emptyHint="Adicione produtos para ver a prévia da foto."/>
    {config.custom_style && <Box mt={2.5}>
      <Typography fontWeight={600} fontSize={14} mb={1}>Mensagem desta campanha</Typography>
      <TemplateEditor value={config.message_template} onChange={v => set({message_template: v})} disclosure={profile?.disclosure_text} minRows={10}/>
    </Box>}
  </Box>;

  /** "Distribuir no período": intervalo que cobre a janela do dia com o total da campanha, com variação de ±20%. */
  const spread = (() => {
    const count = Math.min(config.total_limit, products.length || plan?.matching || config.total_limit);
    const runs = Math.ceil(count / Math.max(1, config.block_size));
    const window = (config.end_hour - config.start_hour) * 60;
    if (runs < 2 || window <= 0) return null;
    const avg = Math.max(1, Math.floor(window / runs));
    const patch = {interval_minutes: Math.max(1, Math.round(avg * .8)), interval_max_minutes: Math.max(1, Math.round(avg * 1.2))};
    if (patch.interval_max_minutes <= patch.interval_minutes) patch.interval_max_minutes = 0;
    if (config.interval_minutes === patch.interval_minutes && config.interval_max_minutes === patch.interval_max_minutes) return null;
    return {count, patch};
  })();
  const rhythmStep = <Stack gap={2.5}>
    {sendModeBox}
    <Box>
      <Typography fontWeight={600} mb={1}>Ritmo</Typography>
      <ToggleButtonGroup exclusive size="small" value={PRESETS.find(([, p]) => p.block_size === config.block_size && p.interval_minutes === config.interval_minutes && !config.interval_max_minutes)?.[0] ?? null}
        onChange={(_, v) => { const p = PRESETS.find(([k]) => k === v); if (p) set(p[1]); }} sx={{flexWrap: 'wrap', mb: 2, '& .MuiToggleButton-root': {textTransform: 'none', px: 1.5}}}>
        {PRESETS.map(([label]) => <ToggleButton key={label} value={label}>{label}</ToggleButton>)}
      </ToggleButtonGroup>
      {spread && <Alert severity="info" sx={{mb: 2}} action={<Button color="inherit" size="small" onClick={() => set(spread.patch)}>Espalhar</Button>}>
        Espalhar os {spread.count} anúncios das {config.start_hour}h às {config.end_hour}h: {config.block_size > 1 ? `${config.block_size} anúncios` : '1 anúncio'} a cada {spread.patch.interval_minutes}
        {spread.patch.interval_max_minutes ? ` a ${spread.patch.interval_max_minutes} min, variando` : ' min'}.
      </Alert>}
      <Stack direction={{xs: 'column', sm: 'row'}} gap={2}>
        <TextField label="Anúncios por execução" type="number" value={config.block_size} onChange={e => set({block_size: Math.min(20, int(e.target.value, 1))})}/>
        <TextField label="Intervalo entre mensagens" type="number" value={config.message_gap_seconds} disabled={config.block_size < 2}
          onChange={e => set({message_gap_seconds: Math.max(20, int(e.target.value, 20))})} helperText="Dentro da mesma execução (mínimo 20 s)"
          InputProps={{endAdornment: <InputAdornment position="end">s</InputAdornment>}}/>
        <TextField label="Intervalo entre execuções" type="number" value={config.interval_minutes} onChange={e => set({interval_minutes: int(e.target.value, 1)})}
          InputProps={{endAdornment: <InputAdornment position="end">min</InputAdornment>}}/>
      </Stack>
    </Box>
    <Box>
      <Typography fontWeight={600} mb={1}>Quando</Typography>
      <Stack direction={{xs: 'column', sm: 'row'}} gap={2}>
        <TextField type="datetime-local" label="Começar em" InputLabelProps={{shrink: true}} value={toLocal(config.start_at)}
          helperText="Vazio = assim que confirmar" onChange={e => set({start_at: e.target.value ? new Date(e.target.value).toISOString() : null})}/>
        <TextField type="datetime-local" label="Terminar em" InputLabelProps={{shrink: true}} value={toLocal(config.end_at)}
          helperText="Vazio = até acabar" onChange={e => set({end_at: e.target.value ? new Date(e.target.value).toISOString() : null})}/>
        <TextField label="Das (hora)" type="number" value={config.start_hour} onChange={e => set({start_hour: Math.min(23, int(e.target.value))})}/>
        <TextField label="Até (hora)" type="number" value={config.end_hour} onChange={e => set({end_hour: Math.min(24, int(e.target.value, 1))})}/>
      </Stack>
      <ToggleButtonGroup size="small" value={config.weekdays} onChange={(_, v) => set({weekdays: (v as number[]).sort()})} sx={{mt: 2, flexWrap: 'wrap', '& .MuiToggleButton-root': {textTransform: 'none', px: 1.5}}} aria-label="Dias da semana">
        {WEEKDAYS.map((d, i) => <ToggleButton key={d} value={i}>{d}</ToggleButton>)}
      </ToggleButtonGroup>
    </Box>
    <Box>
      <Button size="small" onClick={() => setAdvanced(a => !a)} aria-expanded={advanced}>{advanced ? 'Ocultar limites e pausas' : 'Limites e pausas'}</Button>
      <Collapse in={advanced}>
        <Stack direction={{xs: 'column', sm: 'row'}} gap={2} mt={1.5} flexWrap="wrap">
          <TextField label="Intervalo máximo (variável)" type="number" value={config.interval_max_minutes || ''} placeholder="Fixo"
            onChange={e => set({interval_max_minutes: int(e.target.value)})} helperText="Sorteia entre o mínimo e o máximo"
            InputProps={{endAdornment: <InputAdornment position="end">min</InputAdornment>}}/>
          <TextField label="Limite por dia" type="number" value={config.daily_limit || ''} placeholder="Sem limite" onChange={e => set({daily_limit: int(e.target.value)})}/>
          <TextField label="Limite por grupo por dia" type="number" value={config.group_daily_limit || ''} placeholder="Sem limite" onChange={e => set({group_daily_limit: int(e.target.value)})}/>
          <TextField label="Reutilizar produto após" type="number" value={config.reuse_days ?? ''} placeholder="Padrão do grupo"
            onChange={e => set({reuse_days: e.target.value === '' ? null : int(e.target.value)})} helperText="No mesmo grupo. Vazio usa o prazo do cadastro do grupo."
            InputProps={{endAdornment: <InputAdornment position="end">dias</InputAdornment>}}/>
          <TextField label="Pausar a cada" type="number" value={config.pause_every || ''} placeholder="Nunca" onChange={e => set({pause_every: int(e.target.value)})}
            InputProps={{endAdornment: <InputAdornment position="end">anúncios</InputAdornment>}}/>
          <TextField label="Duração da pausa" type="number" value={config.pause_minutes || ''} disabled={!config.pause_every} onChange={e => set({pause_minutes: int(e.target.value)})}
            InputProps={{endAdornment: <InputAdornment position="end">min</InputAdornment>}}/>
        </Stack>
      </Collapse>
    </Box>
  </Stack>;

  const marks = (config.custom_style ? [config.watermark_text, config.watermark_handle] : [profile?.watermark_text, profile?.watermark_handle]).filter(Boolean) as string[];
  const reviewStep = !plan ? <Typography>Calculando…</Typography> : <Stack gap={2}>
    <Box sx={{display: 'grid', gridTemplateColumns: {xs: '1fr', sm: '180px 1fr'}, rowGap: 1, columnGap: 2, fontSize: 14.5}}>
      {[['Nome', config.name || 'sem nome'],
        ['Mensagem e foto', config.custom_style ? 'Personalizadas nesta campanha' : 'Padrão do perfil'],
        ['Forma de envio', config.send_mode === 'image' ? `Foto + texto${marks.length ? ` (marca d'água: ${marks.join(' / ')})` : ''}` : 'Texto com prévia do link'],
        ['Nichos', niches.filter(n => config.niche_ids.includes(n.id)).map(n => n.name).join(', ') || 'nenhum'],
        ['Categorias oficiais', config.ml_categories.map(c => c.name || c.id).join(', ') || 'qualquer'],
        ['Produtos', products.length ? `${products.length} na campanha, ${plan.selected} usados` : `${plan.matching} encontrados, ${plan.selected} usados`],
        ['Filtros antigos', [config.categories.length && `Categorias: ${config.categories.join(', ')}`, config.exclude_categories.length && `sem ${config.exclude_categories.join(', ')}`,
          config.tags.length && `tags (${config.tag_mode === 'all' ? 'todas' : 'qualquer'}): ${config.tags.join(', ')}`, config.exclude_tags.length && `sem as tags ${config.exclude_tags.join(', ')}`]
          .filter(Boolean).join('; ') || 'Todos os produtos prontos'],
        ['Distribuição', strategyLabel[config.strategy][0]],
        ['Grupos', plan.per_group.map(g => `${g.group} (${g.count})`).join(', ') || 'nenhum'],
        ['Ritmo', `${rhythm(config)}, das ${config.start_hour}h às ${config.end_hour}h`],
        ['Início previsto', dateTime(plan.start) || 'sem anúncios'], ['Término previsto', dateTime(plan.end) || ''],
        ['Total de mensagens', String(plan.messages)]].map(([k, v]) => <Fragment key={k}><Typography color="text.secondary" fontSize={14}>{k}</Typography><Typography fontSize={14.5}>{v}</Typography></Fragment>)}
    </Box>
    {plan.items.length > 0 && <Box>
      <Typography fontWeight={650} mb={1}>Primeiros envios</Typography>
      <Card sx={{maxHeight: 300, overflow: 'auto'}}>{plan.items.slice(0, 40).map((i, n) =>
        <Box key={n} sx={{display: 'grid', gridTemplateColumns: {xs: '90px 1fr', sm: '110px 1fr 200px'}, gap: 1.5, px: 1.5, py: .9, fontSize: 14, borderBottom: `1px solid ${tokens.line}`}}>
          <Box color="text.secondary">{dateTime(i.at)}</Box><Box sx={{overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{i.title}</Box>
          <Box color="text.secondary" sx={{display: {xs: 'none', sm: 'block'}, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap'}}>{i.group}</Box></Box>)}</Card>
    </Box>}
  </Stack>;

  const blocking = step === 0 ? stepErrors[0] : step === 3 ? stepErrors[1] : step === 4 ? stepErrors[2] : step === 6 ? stepErrors.find(Boolean) : '';
  return <>
    <PageHeader title={id ? 'Editar campanha' : 'Nova campanha'} description={status === 'paused' ? 'Ao agendar de novo, o que ainda não saiu é replanejado a partir de agora.' : 'Nada é enviado até você confirmar na revisão.'}
      actions={<Button component={Link} to="/campaigns">Voltar para campanhas</Button>}/>
    <Stepper nonLinear activeStep={step} alternativeLabel={!desktop} sx={{mb: 3}}>
      {STEPS.map((label, i) => <Step key={label} completed={i < step}><StepButton onClick={() => goTo(i)}>{desktop || i === step ? label : ''}</StepButton></Step>)}
    </Stepper>
    {error && <Alert severity="error" sx={{mb: 2}} onClose={() => setError('')}>{error}</Alert>}
    {notice && <Alert severity="success" sx={{mb: 2}} onClose={() => setNotice('')}>{notice}</Alert>}
    {picking && campaignId && <ProductPickerDialog open campaignId={campaignId} inCampaign={products.map(p => p.product_id)}
      onClose={() => setPicking(false)}
      onAdded={n => { setNotice(`${n} produto(s) adicionado(s) à campanha.`); loadProducts(campaignId); }}/>}
    <Box sx={{display: 'grid', gap: 3, gridTemplateColumns: {xs: '1fr', md: 'minmax(0, 1fr) 320px'}, alignItems: 'start'}}>
      <Card sx={{p: {xs: 2, md: 3}}}>
        <Typography variant="h5" component="h2" mb={2.5}>{STEPS[step]}</Typography>
        {[infoStep, nicheStep, searchStep, selectionStep, groupsStep, rhythmStep, reviewStep][step]}
        <Stack direction="row" justifyContent="space-between" gap={1} mt={4} flexWrap="wrap">
          <Button disabled={step === 0} onClick={() => setStep(s => s - 1)}>Voltar</Button>
          <Stack direction="row" gap={1} alignItems="center" flexWrap="wrap">
            {blocking && <Typography variant="body2" color="error.main">{blocking}</Typography>}
            <Button variant="outlined" disabled={saving || !config.name.trim()} onClick={() => save(false)}>Salvar rascunho</Button>
            {step < 6 ? <Button variant="contained" disabled={Boolean(blocking)} onClick={() => goTo(step + 1)}>Continuar</Button>
              : <Button variant="contained" disabled={saving || planning || Boolean(blocking)} onClick={() => save(true)}>
                {saving ? 'Agendando…' : `Agendar ${plan?.messages ?? 0} anúncio(s)`}</Button>}
          </Stack>
        </Stack>
      </Card>
      <Summary plan={plan} loading={planning} config={config} productCount={legacy && !products.length ? null : products.length}
        onRespectLimit={limit => set({group_daily_limit: limit})}/>
    </Box>
  </>;
}
