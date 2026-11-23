import {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {Alert, Box, Button, Card, CardContent, Checkbox, Collapse, FormControlLabel, Grid, Stack, Table, TableBody, TableCell, TableHead, TableRow, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {Log, Settings} from '../types/models';
import type {CampaignOptions} from '../types/campaign';
import {Feedback, Loading} from '../components/Feedback';
import {PageHeader} from '../components/Ui';
import {MultiPick, useConfirm} from '../components/Bulk';
import {GroupPicker} from '../components/Fields';
const MARKETPLACES = ['Mercado Livre', 'Amazon', 'Magalu', 'Shopee'].map(name => ({name}));

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null), [logs, setLogs] = useState<Log[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<{name: string; count?: number}[]>([]);
  const confirm = useConfirm();
  const [error, setError] = useState(''), [notice, setNotice] = useState(''), [loading, setLoading] = useState(true);
  const loadLogs = () => api.get<Log[]>('/automations/logs').then(r => setLogs(r.data)).catch(e => setError(apiError(e, 'Falha ao carregar o histórico.')));
  const load = () => {
    setLoading(true);
    api.get<Settings>('/automations/settings').then(s => { setSettings(s.data); setError(''); }).catch(e => setError(apiError(e, 'Falha ao carregar as configurações.'))).finally(() => setLoading(false));
    loadLogs();
    api.get<CampaignOptions>('/campaigns/options').then(r => setCategoryOptions(r.data.categories)).catch(() => {});
  };
  useEffect(load, []);

  const save = async () => {
    if (!settings) return;
    setError(''); setNotice('');
    try {
      const {id: _id, name: _name, default_template: _d, ...payload} = settings;
      const r = await api.put<Settings>('/automations/settings', payload);
      setSettings(r.data); setNotice('Configurações salvas.');
    } catch (e) { setError(apiError(e, 'Falha ao salvar.')); }
  };
  const toggle = (key: keyof Settings) => (_: unknown, checked: boolean) => settings && setSettings({...settings, [key]: checked});
  const clearLogs = async () => {
    if (!await confirm.ask('Limpar o histórico do worker?', 'Todos os registros desta tabela são apagados. Produtos e publicações não mudam.', 'Limpar histórico')) return;
    try { const r = await api.delete('/automations/logs'); setLogs([]); setNotice(`${r.data.deleted} registro(s) apagado(s).`); }
    catch (e) { setError(apiError(e, 'Não foi possível limpar o histórico.')); }
  };

  return <>
    <PageHeader title="Configurações" description="Como os produtos cadastrados viram publicações e o histórico do worker."/>
    <Feedback error={error} notice={notice} onRetry={error ? load : undefined} onClose={() => { setError(''); setNotice(''); }}/>
    <Loading show={loading}/>
    {settings && <>
      <Card sx={{mb: 3}}><CardContent>
        <Typography variant="h6" mb={.5}>Produtos cadastrados à mão</Typography>
        <Typography variant="body2" color="text.secondary" mb={1}>Vale para produtos cadastrados pelo link ou pela extensão. Buscas e campanhas têm as próprias regras.</Typography>
        <Stack>
          <FormControlLabel control={<Checkbox checked={settings.enabled} onChange={toggle('enabled')}/>} label="Automação ativa"/>
          <Box sx={{pl: 4, opacity: settings.enabled ? 1 : .5}}>
            <Stack>
              <FormControlLabel disabled={!settings.enabled} control={<Checkbox checked={settings.process_on_create} onChange={toggle('process_on_create')}/>}
                label="Ler os dados do produto assim que cadastrar (lojas que bloqueiam o servidor são lidas pelo navegador)"/>
              <FormControlLabel disabled={!settings.enabled} control={<Checkbox checked={settings.generate_publication} onChange={toggle('generate_publication')}/>}
                label="Criar a publicação sozinho quando o produto ficar pronto"/>
              <FormControlLabel disabled={!settings.enabled} control={<Checkbox checked={settings.require_approval} onChange={toggle('require_approval')}/>}
                label="Exigir aprovação antes do envio (desmarcado: as publicações entram direto em Prontas)"/>
            </Stack>
            <Collapse in={settings.enabled && settings.generate_publication}>
              <Typography variant="body2" color="text.secondary" mt={1.5} mb={1.5}>Criar sozinho só para estes produtos (vazio = todos):</Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}><MultiPick label="Categorias" value={settings.categories} options={categoryOptions}
                  onChange={v => setSettings({...settings, categories: v})}/></Grid>
                <Grid item xs={12} md={6}><MultiPick label="Lojas" value={settings.marketplaces} options={MARKETPLACES}
                  onChange={v => setSettings({...settings, marketplaces: v})} helper="A loja é preenchida pelo link do produto."/></Grid>
              </Grid>
            </Collapse>
          </Box>
        </Stack>
        <Box mt={2} maxWidth={520}>
          <GroupPicker label="Grupo padrão do WhatsApp" value={settings.whatsapp_group_name || ''} onChange={v => setSettings({...settings, whatsapp_group_name: v})}
            helperText="Usado quando uma publicação é criada sem grupo."/>
        </Box>
      </CardContent></Card>

      <Alert severity="info" sx={{mb: 3}} action={<Button color="inherit" size="small" component={Link} to="/profile?tab=style">Abrir</Button>}>
        O modelo da mensagem, a identificação de publicidade (#publi), a marca d'água e a forma de envio das ofertas avulsas ficam em Meu perfil, aba Mensagem e foto.</Alert>
      <Box mb={4}><Button variant="contained" onClick={save}>Salvar configurações</Button></Box>
    </>}

    <Stack direction="row" justifyContent="space-between" alignItems="center" mb={1}>
      <Typography variant="h6">Histórico do worker</Typography>
      <Stack direction="row" gap={1}><Button onClick={loadLogs}>Atualizar</Button><Button color="error" disabled={!logs.length} onClick={clearLogs}>Limpar histórico</Button></Stack>
    </Stack>
    <Card sx={{overflowX: 'auto'}}><Table size="small">
      <TableHead><TableRow>{['Data', 'Tarefa', 'Produto', 'Estado', 'Tentativa', 'Detalhe'].map(x => <TableCell key={x}>{x}</TableCell>)}</TableRow></TableHead>
      <TableBody>{logs.map(l => <TableRow key={l.id}>
        <TableCell sx={{whiteSpace: 'nowrap'}}>{new Date(l.created_at).toLocaleString()}</TableCell><TableCell>{l.task_type}</TableCell>
        <TableCell>{l.product_id ?? ''}</TableCell><TableCell>{l.status}</TableCell><TableCell>{l.attempt}</TableCell><TableCell>{l.detail}</TableCell>
      </TableRow>)}{!logs.length && <TableRow><TableCell colSpan={6}>Sem registros.</TableCell></TableRow>}</TableBody>
    </Table></Card>
    {confirm.dialog}
  </>;
}
