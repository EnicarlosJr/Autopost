import {useEffect, useRef, useState} from 'react';
import {Box, Chip, Grid, Stack, TextField, Tooltip, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import WhatsAppPreview from './WhatsAppPreview';

type Variables = {line: Record<string, string>; inline: Record<string, string>; default_template: string};

// Layouts prontos. O #publi não entra aqui: ele é acrescentado no envio, sempre na primeira linha.
const FOOTER = '_Preço e estoque podem mudar a qualquer momento._';
export const TEMPLATE_PRESETS: [string, string][] = [
  ['Direto ao ponto', '*{titulo}*\n💸 *R$ {preco_por}*{condicao}{desconto}\n👉 {link}'],
  ['Desconto em destaque', `🚨 *BAIXOU O PREÇO* 🚨\n\n*{titulo}*\n\nDe ~R$ {preco_de}~\nPor *R$ {preco_por}*{condicao}{desconto}\n\n🔗 {link}\n\n${FOOTER}`],
  ['Com a loja', `🛍️ *{titulo}*\n🏪 Vendido por {loja}\n\n❌ De ~R$ {preco_de}~\n✅ Por *R$ {preco_por}*{condicao}{desconto}\n\n👉 Garanta o seu: {link}\n\n${FOOTER}`],
];

/** Editor do modelo da mensagem: variáveis clicáveis, modelos prontos e prévia ao vivo (com o #publi no topo). */
export default function TemplateEditor({value, onChange, disclosure, minRows = 12}: {value: string; onChange: (v: string) => void;
  disclosure?: string; minRows?: number}) {
  const [variables, setVariables] = useState<Variables | null>(null);
  const [preview, setPreview] = useState<{product_title: string; outgoing: string} | null>(null), [previewError, setPreviewError] = useState('');
  const editor = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { api.get<Variables>('/automations/template-variables').then(r => setVariables(r.data)).catch(() => {}); }, []);
  const template = value || variables?.default_template || '';
  useEffect(() => {
    if (!template) return;
    const t = setTimeout(() => api.post('/automations/template-preview', {template, disclosure: disclosure ?? null})
      .then(r => { setPreview(r.data); setPreviewError(''); })
      .catch(e => setPreviewError(apiError(e, 'Modelo inválido.'))), 400);
    return () => clearTimeout(t);
  }, [template, disclosure]);
  const insert = (name: string) => {
    const el = editor.current, token = `{${name}}`;
    if (!el) { onChange(template + token); return; }
    const start = el.selectionStart, end = el.selectionEnd;
    onChange(template.slice(0, start) + token + template.slice(end));
    setTimeout(() => { el.focus(); el.setSelectionRange(start + token.length, start + token.length); });
  };
  return <Box>
    <Typography variant="body2" color="text.secondary" mb={1}>Clique numa variável para inserir. Se o produto não tiver o dado de uma variável azul,
      a linha inteira some; as cinzas somem sem apagar a linha. Use *negrito*, _itálico_ e ~riscado~ como no WhatsApp.</Typography>
    <Stack direction="row" flexWrap="wrap" gap={.75} mb={1.5}>
      {variables && Object.entries(variables.line).map(([name, help]) => <Tooltip key={name} title={help}><Chip size="small" color="primary" variant="outlined" label={`{${name}}`} onClick={() => insert(name)}/></Tooltip>)}
      {variables && Object.entries(variables.inline).map(([name, help]) => <Tooltip key={name} title={help}><Chip size="small" variant="outlined" label={`{${name}}`} onClick={() => insert(name)}/></Tooltip>)}
    </Stack>
    <Stack direction="row" flexWrap="wrap" gap={.75} alignItems="center" mb={2}>
      <Typography variant="caption" mr={.5}>Modelos prontos:</Typography>
      <Chip size="small" label="Padrão" color={variables && template === variables.default_template ? 'primary' : 'default'}
        onClick={() => variables && onChange(variables.default_template)}/>
      {TEMPLATE_PRESETS.map(([label, text]) => <Chip key={label} size="small" label={label} color={template === text ? 'primary' : 'default'} onClick={() => onChange(text)}/>)}
    </Stack>
    <Grid container spacing={2}>
      <Grid item xs={12} md={7}>
        <TextField inputRef={editor} fullWidth multiline minRows={minRows} label="Modelo da mensagem" value={template}
          onChange={e => onChange(e.target.value)} error={Boolean(previewError)} helperText={previewError || 'O #publi entra sozinho na primeira linha, no envio.'}/>
      </Grid>
      <Grid item xs={12} md={5}>
        <Typography variant="body2" color="text.secondary" mb={1}>Como chega no grupo{preview?.product_title ? `, com "${preview.product_title}"` : ''}</Typography>
        {preview && <WhatsAppPreview message={preview.outgoing}/>}
      </Grid>
    </Grid>
  </Box>;
}
