import {Fragment, type ReactNode} from 'react';
import {Box, Typography} from '@mui/material';

// Mesmas marcações que o WhatsApp formata: *negrito*, _itálico_, ~riscado~ e ```monoespaçado```.
const MARKS: Record<string, (text: ReactNode, key: number) => ReactNode> = {
  '*': (t, k) => <strong key={k}>{t}</strong>,
  '_': (t, k) => <em key={k}>{t}</em>,
  '~': (t, k) => <s key={k}>{t}</s>,
  '```': (t, k) => <Box component="code" key={k} sx={{fontFamily: 'monospace'}}>{t}</Box>,
};
const PATTERN = /(```[^`\n]+```|\*[^*\n]+\*|_[^_\n]+_|~[^~\n]+~)/g;
const LINK = /(https?:\/\/[^\s]+)/g;

function links(text: string, base: number): ReactNode[] {
  return text.split(LINK).map((part, i) => /^https?:\/\//.test(part)
    ? <Box component="span" key={base + i} sx={{color: '#027eb5', wordBreak: 'break-all'}}>{part}</Box>
    : <Fragment key={base + i}>{part}</Fragment>);
}

function format(line: string): ReactNode[] {
  return line.split(PATTERN).map((part, i) => {
    if (!part) return null;
    const mark = part.startsWith('```') && part.length > 6 ? '```' : part[0];
    const size = mark.length;
    if (MARKS[mark] && part.length > size * 2 && part.endsWith(mark) && part.trim() === part) {
      return MARKS[mark](links(part.slice(size, -size), i * 100), i);
    }
    return <Fragment key={i}>{links(part, i * 100)}</Fragment>;
  });
}

/** Prévia no formato do WhatsApp: só o texto, com a formatação aplicada como na conversa. */
export default function WhatsAppPreview({message}: {message: string}) {
  const lines = message.split('\n');
  return <Box sx={{bgcolor: '#efeae2', p: 1.5, borderRadius: 2, maxWidth: 380}}>
    <Box sx={{bgcolor: '#d9fdd3', borderRadius: 2, px: 1.25, py: 0.75, boxShadow: '0 1px 0.5px rgba(0,0,0,.13)'}}>
      <Typography component="div" sx={{fontSize: 14, wordBreak: 'break-word'}}>
        {lines.map((line, i) => <Fragment key={i}>{format(line)}{i < lines.length - 1 && <br/>}</Fragment>)}
      </Typography>
    </Box>
  </Box>;
}
