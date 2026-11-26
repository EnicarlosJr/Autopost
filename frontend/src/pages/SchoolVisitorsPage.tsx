// Responsáveis que se identificaram nas páginas públicas das listas escolares (nome do aluno e turma).
import {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {Box, Button, Card, Checkbox, MenuItem, Stack, TextField, Typography} from '@mui/material';
import {api, apiError} from '../services/api';
import {usePaged} from '../hooks/usePaged';
import type {SchoolListSummary, SchoolVisitor} from '../types/school';
import {Empty, Feedback, LoadMore, Loading} from '../components/Feedback';
import {Meta, PageHeader} from '../components/Ui';
import {BulkBar, SelectAll, SelectMatching, fetchAllIds, inBatches, useConfirm, useSelection} from '../components/Bulk';

const when = (iso: string | null) => iso ? new Date(iso).toLocaleString('pt-BR', {dateStyle: 'short', timeStyle: 'short'}) : '';

export default function SchoolVisitorsPage() {
  const [lists, setLists] = useState<SchoolListSummary[]>([]);
  const [listId, setListId] = useState<number | ''>(''), [q, setQ] = useState(''), [notice, setNotice] = useState('');
  const params = {list_id: listId || undefined, q: q.trim() || undefined};
  const page = usePaged<SchoolVisitor>('/school-visitors', params, 50);
  const sel = useSelection(); const confirm = useConfirm();
  useEffect(() => { api.get<SchoolListSummary[]>('/school-lists').then(r => setLists(r.data)).catch(() => {}); }, []);
  useEffect(() => sel.clear(), [listId, q]); // eslint-disable-line react-hooks/exhaustive-deps
  const listName = (id: number | null) => { const l = lists.find(x => x.id === id); return l ? `${l.grade} ${l.year}` : 'lista excluída'; };
  const pageIds = page.items.map(v => v.id);
  const pageSelected = pageIds.length > 0 && pageIds.every(id => sel.has(id));

  const remove = async () => {
    if (!await confirm.ask('Excluir registros?', `${sel.count} registro(s) de responsáveis saem do Autopost. Quem já entrou vai precisar se identificar de novo.`, 'Excluir registros')) return;
    try {
      const result = await inBatches(sel.ids, chunk => api.post('/school-visitors/bulk/delete', {ids: chunk}));
      setNotice(`${result.deleted || 0} registro(s) excluído(s).`); sel.clear(); page.reload();
    } catch (e) { page.setError(apiError(e, 'Não foi possível excluir.')); }
  };
  const exportCsv = async () => {
    try {
      const r = await api.get('/school-visitors/export.csv', {params, responseType: 'blob'});
      const href = URL.createObjectURL(r.data as Blob);
      const a = document.createElement('a'); a.href = href; a.download = 'responsaveis.csv'; a.click();
      setTimeout(() => URL.revokeObjectURL(href), 2000);
    } catch (e) { page.setError(apiError(e, 'Não foi possível exportar.')); }
  };

  return <>
    <PageHeader title="Responsáveis" description={<>Quem se identificou nas páginas das listas escolares: nome do aluno, turma e acessos. <Link to="/school-lists">Voltar às listas</Link></>}
      actions={<Button variant="outlined" onClick={exportCsv}>Exportar planilha (CSV)</Button>}/>
    <Feedback error={page.error} notice={notice} onRetry={() => page.reload()} onClose={() => { page.setError(''); setNotice(''); }}/>
    <Stack direction={{xs: 'column', sm: 'row'}} gap={1.5} mb={2}>
      <TextField select size="small" label="Lista" value={listId} onChange={e => setListId(e.target.value === '' ? '' : Number(e.target.value))} sx={{minWidth: 240}}>
        <MenuItem value="">Todas as listas</MenuItem>
        {lists.map(l => <MenuItem key={l.id} value={l.id}>{l.grade} {l.year} · {l.school || 'sem escola'}</MenuItem>)}
      </TextField>
      <TextField size="small" label="Buscar aluno" value={q} onChange={e => setQ(e.target.value)} sx={{minWidth: 240}}/>
      <Box flex={1}/>
      <Typography alignSelf="center" color="text.secondary" fontSize={14}>{page.total} registro(s)</Typography>
    </Stack>
    <SelectAll total={pageIds.length} selected={pageIds.filter(id => sel.has(id)).length} onAll={() => sel.add(pageIds)} onNone={() => sel.setAll(sel.ids.filter(id => !pageIds.includes(id)))}/>
    <SelectMatching pageCount={pageIds.length} pageSelected={pageSelected} selected={sel.count} total={page.total} noun="registros"
      onSelectAll={async () => sel.setAll(await fetchAllIds('/school-visitors', params))} onClear={sel.clear}/>
    <Loading show={page.loading}/>
    {!page.loading && !page.items.length && <Empty text="Ninguém se identificou ainda. Publique uma lista e mande o link no grupo."/>}
    <Stack gap={1}>
      {page.items.map(v => <Card key={v.id} sx={{p: 1.5, display: 'flex', alignItems: 'center', gap: 1.5}}>
        <Checkbox checked={sel.has(v.id)} onChange={() => sel.toggle(v.id)} inputProps={{'aria-label': `Selecionar ${v.student_name}`}}/>
        <Box minWidth={0} flex={1}>
          <Typography fontWeight={600}>{v.student_name}</Typography>
          <Meta items={[v.turma, v.school, listName(v.list_id), `${v.visits} acesso(s)`, `desde ${when(v.created_at)}`, `último ${when(v.last_seen_at)}`]}/>
        </Box>
      </Card>)}
    </Stack>
    <LoadMore show={page.hasMore} onClick={page.loadMore} loading={page.loading}/>
    <BulkBar count={sel.count} noun="selecionado(s)" onClear={sel.clear}>
      <Button variant="outlined" onClick={remove}>Excluir registros</Button>
    </BulkBar>
    {confirm.dialog}
  </>;
}
