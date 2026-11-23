import {useEffect, useState} from 'react';
import {Autocomplete, Box, Stack, TextField, ToggleButton, ToggleButtonGroup, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import type {Product} from '../types/product';
import {tokens} from '../theme';

/** Nomes dos grupos cadastrados em Grupos. */
export function useGroupNames(): string[] {
  const [names, setNames] = useState<string[]>([]);
  useEffect(() => {
    let alive = true;
    api.get<{group_name: string}[]>('/group-schedules').then(r => { if (alive) setNames(r.data.map(g => g.group_name)); }).catch(() => {});
    return () => { alive = false; };
  }, []);
  return names;
}

/** Grupo do WhatsApp: escolhe um cadastrado ou digita o nome exato. */
export function GroupPicker({value, onChange, label = 'Grupo do WhatsApp', helperText, size}: {value: string; onChange: (v: string) => void;
  label?: string; helperText?: string; size?: 'small' | 'medium'}) {
  const names = useGroupNames();
  return <Autocomplete freeSolo options={names} value={value} size={size}
    onChange={(_, v) => onChange(typeof v === 'string' ? v : '')}
    onInputChange={(_, v, reason) => { if (reason === 'input' || reason === 'clear') onChange(v); }}
    renderInput={params => <TextField {...params} label={label}
      helperText={helperText ?? (names.length ? 'Escolha um grupo cadastrado ou digite o nome exato.' : 'Nome exato do grupo no WhatsApp.')}/>}/>;
}

/** Produto pronto, com busca pelo nome (não carrega a lista inteira). */
export function ProductPicker({value, onChange}: {value: Product | null; onChange: (p: Product | null) => void}) {
  const [query, setQuery] = useState(''), [options, setOptions] = useState<Product[]>([]), [loading, setLoading] = useState(false);
  useEffect(() => {
    let alive = true; setLoading(true);
    const t = setTimeout(() => {
      api.get<Product[]>('/products', {params: {status: 'processed', q: query || undefined, limit: 30}})
        .then(r => { if (alive) setOptions(r.data); }).catch(() => {}).finally(() => { if (alive) setLoading(false); });
    }, 300);
    return () => { alive = false; clearTimeout(t); };
  }, [query]);
  const brl = (n: number | null) => n == null ? 'sem preço' : n.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
  return <Autocomplete options={options} value={value} loading={loading} filterOptions={(x: Product[]) => x}
    getOptionLabel={(p: Product) => p.title || `Produto ${p.id}`} isOptionEqualToValue={(a: Product, b: Product) => a.id === b.id}
    onChange={(_, v) => onChange((v as Product | null) ?? null)} onInputChange={(_, v, reason) => { if (reason === 'input') setQuery(v); }}
    noOptionsText={query ? 'Nenhum produto pronto com esse nome.' : 'Nenhum produto pronto.'}
    renderOption={(props, p: Product) => <li {...props} key={p.id}><Box flex={1} minWidth={0}><Typography fontSize={14} noWrap>{p.title || `Produto ${p.id}`}</Typography>
      <Typography variant="caption">{brl(p.price)}{p.store ? ` em ${p.store}` : ''}</Typography></Box></li>}
    renderInput={params => <TextField {...params} label="Produto" placeholder="Digite parte do nome"/>}/>;
}

type SendMode = 'preview' | 'image';
export type SendModePatch = {send_mode?: SendMode; watermark_text?: string; watermark_handle?: string};

/** Forma de envio (texto com prévia do link ou foto + texto) com a marca d'água e a prévia da foto. */
export function SendModeFields({mode, text, handle, onChange, sampleUrl, sampleNote, emptyHint, refreshKey, fixed = false, showMarks = false, previewParams}: {mode: SendMode; text: string;
  handle: string; onChange: (patch: SendModePatch) => void; sampleUrl: string | null; sampleNote: string; emptyHint?: string; refreshKey?: unknown;
  fixed?: boolean;                               // marca d'água vem do perfil: mostra, mas não edita aqui
  showMarks?: boolean;                           // mostra a marca d'água mesmo no modo texto (padrão do perfil)
  previewParams?: Record<string, unknown>}) {    // outros dados da prévia (selo de publicidade, desconto)
  const [sample, setSample] = useState(''), [sampleError, setSampleError] = useState('');
  useEffect(() => {
    if ((mode !== 'image' && !showMarks) || !sampleUrl) return;
    let alive = true, url = '';
    const t = setTimeout(async () => {
      try {
        const r = await api.get(sampleUrl, {responseType: 'blob', params: {title: text, handle, ...previewParams}});
        url = URL.createObjectURL(r.data);
        if (alive) { setSample(url); setSampleError(''); }
      } catch (e) { if (alive) { setSample(''); setSampleError(apiError(e, 'Não foi possível gerar a prévia da foto.')); } }
    }, 600);
    return () => { alive = false; clearTimeout(t); if (url) URL.revokeObjectURL(url); };
  }, [mode, showMarks, text, handle, sampleUrl, refreshKey, JSON.stringify(previewParams ?? {})]); // eslint-disable-line react-hooks/exhaustive-deps
  return <Box>
    <ToggleButtonGroup exclusive size="small" value={mode} onChange={(_, v: SendMode | null) => v && onChange({send_mode: v})}
      sx={{flexWrap: 'wrap', '& .MuiToggleButton-root': {textTransform: 'none', px: 2}}}>
      <ToggleButton value="preview">Texto com prévia do link</ToggleButton>
      <ToggleButton value="image">Foto + texto</ToggleButton>
    </ToggleButtonGroup>
    <Typography variant="body2" color="text.secondary" mt={.75}>
      {mode === 'image'
        ? 'Envia a foto do produto em 1080 x 1080 (maior qualidade disponível, sempre do mesmo tamanho) com a mensagem como legenda. O link fica clicável no texto.'
        : 'Envia só o texto; o WhatsApp monta o cartão com foto e título do link. Use "Ensaiar no WhatsApp" na Fila para conferir se a prévia aparece.'}
    </Typography>
    {(mode === 'image' || showMarks) && <Stack direction={{xs: 'column', md: 'row'}} gap={2.5} mt={2} alignItems={{md: 'flex-start'}}>
      {fixed ? <Box flex={1}>
        <Typography variant="body2" fontWeight={600}>Marca d'água do perfil</Typography>
        <Typography variant="body2" color="text.secondary">{text || handle ? [text, handle].filter(Boolean).join('  ·  ') : 'Sem faixa de marca d\'água.'}</Typography>
        <Typography variant="caption" display="block" mt={.5}>Para mudar só nesta campanha, desligue "Usar o padrão do perfil".</Typography>
      </Box> : <Stack gap={2} flex={1}>
        <TextField label="Marca d'água: nome do grupo" value={text} onChange={e => onChange({watermark_text: e.target.value.slice(0, 60)})}
          placeholder="Base 92 | Achados e Ofertas" helperText="Vazio = sem faixa de marca d'água."/>
        <TextField label="Marca d'água: Instagram" value={handle} onChange={e => onChange({watermark_handle: e.target.value.slice(0, 40)})} placeholder="@base92"/>
      </Stack>}
      <Box sx={{width: 260, flexShrink: 0}}>
        {sample && sampleUrl ? <Box component="img" src={sample} alt="Prévia da foto enviada" sx={{width: 260, height: 260, borderRadius: 2, border: `1px solid ${tokens.line}`, display: 'block'}}/>
          : <Box sx={{width: 260, height: 260, borderRadius: 2, border: `1px dashed ${tokens.line}`, display: 'grid', placeItems: 'center', p: 2, textAlign: 'center'}}>
            <Typography variant="body2" color="text.secondary">{!sampleUrl ? (emptyHint || 'Sem produto para a prévia.') : sampleError || 'Gerando a prévia…'}</Typography></Box>}
        <Typography variant="caption" display="block" mt={.5}>{sampleNote}</Typography>
      </Box>
    </Stack>}
  </Box>;
}
