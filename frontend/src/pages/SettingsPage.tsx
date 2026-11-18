import {useEffect, useRef, useState} from 'react';
import {Box, Button, Card, CardContent, Checkbox, Chip, FormControlLabel, Grid, Stack, Table, TableBody, TableCell, TableHead, TableRow, TextField, ToggleButton, ToggleButtonGroup, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {Log, Settings} from '../types/models';
import {Feedback, Loading} from '../components/Feedback';
import {PageHeader} from '../components/Ui';
import WhatsAppPreview from '../components/WhatsAppPreview';

type Variables = {line: Record<string, string>; inline: Record<string, string>};
const splitList = (value: string) => value.split(',').map(x => x.trim()).filter(Boolean);

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null), [logs, setLogs] = useState<Log[]>([]);
  const [categories, setCategories] = useState(''), [marketplaces, setMarketplaces] = useState('');
  const [template, setTemplate] = useState(''), [variables, setVariables] = useState<Variables | null>(null);
  const [preview, setPreview] = useState<{product_title: string; message: string} | null>(null), [previewError, setPreviewError] = useState('');
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [loading, setLoading] = useState(true);
  const editor = useRef<HTMLTextAreaElement>(null);
  const [sample, setSample] = useState(''), [sampleError, setSampleError] = useState('');
  // Prévia da foto das ofertas avulsas, com a marca d'água digitada.
  useEffect(() => {
    if (settings?.send_mode !== 'image') return;
    let alive = true, url = '';
    const t = setTimeout(async () => {
      try {
        const r = await api.get('/automations/sample-image', {responseType: 'blob', params: {title: settings.watermark_text, handle: settings.watermark_handle}});
        url = URL.createObjectURL(r.data);
        if (alive) { setSample(url); setSampleError(''); }
      } catch (e) { if (alive) { setSample(''); setSampleError(apiError(e, 'Não foi possível gerar a prévia da foto.')); } }
    }, 600);
    return () => { alive = false; clearTimeout(t); if (url) URL.revokeObjectURL(url); };
  }, [settings?.send_mode, settings?.watermark_text, settings?.watermark_handle]);

  const loadLogs = () => api.get<Log[]>('/automations/logs').then(r => setLogs(r.data)).catch(e => setError(apiError(e, 'Falha ao carregar o histórico.')));
  const load = () => {
    setLoading(true);
    Promise.all([api.get<Settings>('/automations/settings'), api.get<Variables>('/automations/template-variables')]).then(([s, v]) => {
      setSettings(s.data); setVariables(v.data);
      setCategories(s.data.categories.join(', ')); setMarketplaces(s.data.marketplaces.join(', '));
      setTemplate(s.data.message_template || s.data.default_template); setError('');
    }).catch(e => setError(apiError(e, 'Falha ao carregar as configurações.'))).finally(() => setLoading(false));
    loadLogs();
  };
  useEffect(load, []);

  // Prévia ao vivo do modelo com um produto real (ou de exemplo).
  useEffect(() => {
    if (!template) return;
    const timer = setTimeout(() => api.post('/automations/template-preview', {template})
      .then(r => { setPreview(r.data); setPreviewError(''); })
      .catch(e => setPreviewError(apiError(e, 'Modelo inválido.'))), 400);
    return () => clearTimeout(timer);
  }, [template]);

  const insert = (name: string) => {
    const el = editor.current, token = `{${name}}`;
    if (!el) { setTemplate(t => t + token); return; }
    const start = el.selectionStart, end = el.selectionEnd;
    setTemplate(t => t.slice(0, start) + token + t.slice(end));
    setTimeout(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
  };
  const save = async () => {
    if (!settings) return;
    setError(''); setNotice('');
    try {
      const {id: _id, name: _name, default_template: _d, ...payload} = settings;
      const r = await api.put<Settings>('/automations/settings', {...payload, categories: splitList(categories), marketplaces: splitList(marketplaces), message_template: template});
      setSettings(r.data); setNotice('Configurações salvas. Novas publicações usam o modelo salvo.');
    } catch (e) { setError(apiError(e, 'Falha ao salvar.')); }
  };
  const toggle = (key: keyof Settings) => (_: unknown, checked: boolean) => settings && setSettings({...settings, [key]: checked});

  return <>
    <PageHeader title="Configurações" description="Como os produtos viram publicações e o texto que vai para o grupo."/>
    <Feedback error={error} notice={notice} onRetry={error ? load : undefined} onClose={() => { setError(''); setNotice(''); }}/>
    <Loading show={loading}/>
    {settings && <>
      <Card sx={{mb: 3}}><CardContent>
        <Typography variant="h6" mb={1}>Automação</Typography>
        <Stack>
          <FormControlLabel control={<Checkbox checked={settings.enabled} onChange={toggle('enabled')}/>} label="Automação ativa"/>
          <FormControlLabel control={<Checkbox checked={settings.process_on_create} onChange={toggle('process_on_create')}/>} label="Extrair dados assim que cadastrar (lojas que bloqueiam o servidor são lidas pelo navegador)"/>
          <FormControlLabel control={<Checkbox checked={settings.generate_publication} onChange={toggle('generate_publication')}/>} label="Gerar publicação quando o produto ficar pronto"/>
          <FormControlLabel control={<Checkbox checked={settings.require_approval} onChange={toggle('require_approval')}/>} label="Exigir aprovação antes do envio (desmarcado: publicações entram direto na fila)"/>
        </Stack>
        <Grid container spacing={2} mt={1}>
          <Grid item xs={12} md={6}><TextField fullWidth label="Categorias permitidas (separadas por vírgula)" value={categories} onChange={e => setCategories(e.target.value)}/></Grid>
          <Grid item xs={12} md={6}><TextField fullWidth label="Marketplaces permitidos (separados por vírgula)" value={marketplaces} onChange={e => setMarketplaces(e.target.value)}/></Grid>
          <Grid item xs={12}><TextField fullWidth label="Grupo padrão do WhatsApp (nome exato)" value={settings.whatsapp_group_name || ''} onChange={e => setSettings({...settings, whatsapp_group_name: e.target.value})}/></Grid>
        </Grid>
      </CardContent></Card>

      <Card sx={{mb: 3}}><CardContent>
        <Typography variant="h6" mb={.5}>Forma de envio das ofertas avulsas</Typography>
        <Typography variant="body2" color="text.secondary" mb={1.5}>Vale para as publicações fora de campanha (cada campanha tem a sua). Na Fila dá para trocar só uma publicação em "Editar".</Typography>
        <ToggleButtonGroup exclusive size="small" value={settings.send_mode || 'preview'} onChange={(_, v) => v && setSettings({...settings, send_mode: v})}
          sx={{flexWrap: 'wrap', '& .MuiToggleButton-root': {textTransform: 'none', px: 2}}}>
          <ToggleButton value="preview">Texto com prévia do link</ToggleButton>
          <ToggleButton value="image">Foto + texto</ToggleButton>
        </ToggleButtonGroup>
        {settings.send_mode === 'image' && <Stack direction={{xs: 'column', md: 'row'}} gap={2.5} mt={2} alignItems={{md: 'flex-start'}}>
          <Stack gap={2} flex={1}>
            <Typography variant="body2" color="text.secondary">A foto vai em 1080 x 1080, na maior qualidade disponível e sempre do mesmo tamanho, com a mensagem como legenda.</Typography>
            <TextField label="Marca d'água: nome do grupo" value={settings.watermark_text || ''} onChange={e => setSettings({...settings, watermark_text: e.target.value.slice(0, 60)})}
              placeholder="Base 92 | Achados e Ofertas" helperText="Vazio = sem faixa de marca d'água."/>
            <TextField label="Marca d'água: Instagram" value={settings.watermark_handle || ''} onChange={e => setSettings({...settings, watermark_handle: e.target.value.slice(0, 40)})} placeholder="@base92"/>
          </Stack>
          <Box sx={{width: 260, flexShrink: 0}}>
            {sample ? <Box component="img" src={sample} alt="Prévia da foto enviada" sx={{width: 260, height: 260, borderRadius: 2, display: 'block', border: '1px solid rgba(0,0,0,.12)'}}/>
              : <Box sx={{width: 260, height: 260, borderRadius: 2, border: '1px dashed rgba(0,0,0,.2)', display: 'grid', placeItems: 'center', p: 2, textAlign: 'center'}}>
                <Typography variant="body2" color="text.secondary">{sampleError || 'Gerando a prévia…'}</Typography></Box>}
            <Typography variant="caption" display="block" mt={.5}>Prévia com o produto mais recente.</Typography>
          </Box>
        </Stack>}
      </CardContent></Card>

      <Card sx={{mb: 3}}><CardContent>
        <Typography variant="h6">Modelo da mensagem</Typography>
        <Typography variant="body2" color="text.secondary" mb={2}>Clique numa variável para inserir. Se o produto não tiver o dado de uma variável azul, a linha inteira não aparece; as cinzas somem sem apagar a linha.</Typography>
        <Stack direction="row" flexWrap="wrap" gap={1} mb={2}>
          {variables && Object.entries(variables.line).map(([name, help]) => <Tooltip key={name} title={help}><Chip color="primary" variant="outlined" label={`{${name}}`} onClick={() => insert(name)}/></Tooltip>)}
          {variables && Object.entries(variables.inline).map(([name, help]) => <Tooltip key={name} title={help}><Chip variant="outlined" label={`{${name}}`} onClick={() => insert(name)}/></Tooltip>)}
        </Stack>
        <Grid container spacing={2}>
          <Grid item xs={12} md={7}>
            <TextField inputRef={editor} fullWidth multiline minRows={14} label="Modelo" value={template} onChange={e => setTemplate(e.target.value)} error={Boolean(previewError)} helperText={previewError || ' '}/>
            <Button size="small" onClick={() => setTemplate(settings.default_template)}>Restaurar modelo padrão</Button>
          </Grid>
          <Grid item xs={12} md={5}>
            <Typography variant="body2" color="text.secondary" mb={1}>Prévia{preview?.product_title ? ` com "${preview.product_title}"` : ''}</Typography>
            {preview && <WhatsAppPreview message={preview.message}/>}
          </Grid>
        </Grid>
      </CardContent></Card>
      <Box mb={4}><Button variant="contained" onClick={save}>Salvar configurações</Button></Box>
    </>}

    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
      <Typography variant="h6">Histórico do worker</Typography><Button onClick={loadLogs}>Atualizar</Button>
    </Stack>
    <Card sx={{overflowX: 'auto'}}><Table size="small">
      <TableHead><TableRow>{['Data', 'Tarefa', 'Produto', 'Estado', 'Tentativa', 'Detalhe'].map(x => <TableCell key={x}>{x}</TableCell>)}</TableRow></TableHead>
      <TableBody>{logs.map(l => <TableRow key={l.id}>
        <TableCell sx={{whiteSpace: 'nowrap'}}>{new Date(l.created_at).toLocaleString()}</TableCell><TableCell>{l.task_type}</TableCell>
        <TableCell>{l.product_id ?? ''}</TableCell><TableCell>{l.status}</TableCell><TableCell>{l.attempt}</TableCell><TableCell>{l.detail}</TableCell>
      </TableRow>)}{!logs.length && <TableRow><TableCell colSpan={6}>Sem registros.</TableCell></TableRow>}</TableBody>
    </Table></Card>
  </>;
}
