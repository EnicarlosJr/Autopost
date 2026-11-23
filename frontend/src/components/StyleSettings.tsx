import {useEffect, useState} from 'react';
import {Alert, Box, Button, Card, CardContent, Chip, FormControlLabel, Stack, Switch, TextField, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {Settings} from '../types/models';
import {Feedback, Loading} from './Feedback';
import {SendModeFields} from './Fields';
import TemplateEditor from './TemplateEditor';

const DISCLOSURES = ['#publi', '#publi | link de afiliado', '#publi #afiliado'];

/** Padrão do perfil: identificação de publicidade, modelo da mensagem e foto. As campanhas usam este padrão,
 *  a menos que personalizem. As ofertas avulsas (fora de campanha) usam sempre. */
export default function StyleSettings() {
  const [settings, setSettings] = useState<Settings | null>(null), [loading, setLoading] = useState(true), [saving, setSaving] = useState(false);
  const [error, setError] = useState(''), [notice, setNotice] = useState('');
  const load = () => {
    setLoading(true);
    api.get<Settings>('/automations/settings').then(r => { setSettings(r.data); setError(''); })
      .catch(e => setError(apiError(e, 'Não foi possível carregar o padrão do perfil.'))).finally(() => setLoading(false));
  };
  useEffect(load, []);
  const set = (patch: Partial<Settings>) => setSettings(s => s && {...s, ...patch});
  const disclosureOk = !settings || !settings.disclosure_text.trim() || settings.disclosure_text.toLocaleLowerCase().includes('publi');
  const save = async () => {
    if (!settings) return;
    setSaving(true); setError(''); setNotice('');
    try {
      const {id: _id, name: _name, default_template: _d, updated_at: _u, ...payload} = settings as Settings & {updated_at?: string};
      const r = await api.put<Settings>('/automations/settings', payload);
      setSettings(r.data); setNotice('Padrão salvo. Vale para as próximas publicações e para as campanhas que usam o padrão do perfil.');
    } catch (e) { setError(apiError(e, 'Não foi possível salvar.')); }
    finally { setSaving(false); }
  };

  return <Box>
    <Feedback error={error} notice={notice} onRetry={error ? load : undefined} onClose={() => { setError(''); setNotice(''); }}/>
    <Loading show={loading}/>
    {settings && <Stack gap={2.5}>
      <Alert severity="info">Este é o padrão do perfil. As campanhas usam este padrão, a menos que você personalize a mensagem e a foto na própria campanha
        (etapa Regras de automação). A identificação de publicidade vale sempre, inclusive nas campanhas personalizadas.</Alert>

      <Card><CardContent>
        <Typography variant="h6" component="h2" mb={.5}>Identificação de publicidade</Typography>
        <Typography variant="body2" color="text.secondary" mb={2}>Vai na primeira linha de toda mensagem e num selo no canto da foto.
          O programa de afiliados do Mercado Livre pede que você se identifique como afiliado; o texto precisa ter #publi.</Typography>
        <Stack direction={{xs: 'column', sm: 'row'}} gap={1.5} alignItems={{sm: 'flex-start'}}>
          <TextField label="Texto" value={settings.disclosure_text} sx={{minWidth: 280}} onChange={e => set({disclosure_text: e.target.value.slice(0, 40)})}
            error={!disclosureOk} helperText={disclosureOk ? 'Vazio usa "#publi".' : 'Precisa ter #publi.'}/>
          <Stack direction="row" gap={.75} flexWrap="wrap" pt={{sm: 1.25}}>{DISCLOSURES.map(d =>
            <Chip key={d} label={d} size="small" color={settings.disclosure_text === d ? 'primary' : 'default'} onClick={() => set({disclosure_text: d})}/>)}</Stack>
        </Stack>
      </CardContent></Card>

      <Card><CardContent>
        <Typography variant="h6" component="h2" mb={1}>Modelo da mensagem</Typography>
        <TemplateEditor value={settings.message_template} onChange={v => set({message_template: v})} disclosure={settings.disclosure_text}/>
      </CardContent></Card>

      <Card><CardContent>
        <Typography variant="h6" component="h2" mb={.5}>Foto</Typography>
        <Typography variant="body2" color="text.secondary" mb={1.5}>A forma de envio abaixo vale para as ofertas avulsas (fora de campanha); cada campanha escolhe a sua.
          A marca d'água e o selo de desconto valem para todas as fotos que usam o padrão do perfil.</Typography>
        <SendModeFields mode={settings.send_mode || 'preview'} text={settings.watermark_text || ''} handle={settings.watermark_handle || ''}
          onChange={patch => set(patch)} sampleUrl="/automations/sample-image" sampleNote="Prévia com o produto mais recente." showMarks
          previewParams={{disclosure: settings.disclosure_text, show_discount: settings.show_discount}}/>
        <FormControlLabel sx={{mt: 1.5}} control={<Switch checked={settings.show_discount} onChange={e => set({show_discount: e.target.checked})}/>}
          label='Selo de desconto na foto (ex.: "-30% OFF"), quando o produto tem preço anterior'/>
      </CardContent></Card>

      <Box><Button variant="contained" disabled={saving || !disclosureOk} onClick={save}>{saving ? 'Salvando…' : 'Salvar padrão do perfil'}</Button></Box>
    </Stack>}
  </Box>;
}
