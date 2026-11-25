-- Exporta os nichos "B92 ..." deste banco como um script SQL que recria tudo em outra máquina.
-- Uso (PowerShell, na pasta do Autopost):
--   Get-Content .\exportar-nichos-b92.sql | docker compose exec -T db psql -U autopost -d autopost -At -o /tmp/nichos-b92.sql
--   docker compose cp db:/tmp/nichos-b92.sql .\nichos-b92.sql
-- O arquivo gerado (nichos-b92.sql) e o que vai para a outra maquina.

select 'begin;'
union all
select string_agg(stmt, E'\n' order by ord) from (
  select n.id * 1000 as ord, format(
    'insert into niches (owner_id, name, description, favorite, tags, include_keywords, exclude_keywords, gender, created_at, updated_at) '
    'select u.id, %L, %L, %L, %L, %L, %L, %L, now(), now() from (select id from users order by id limit 1) u '
    'where not exists (select 1 from niches x where x.owner_id = u.id and x.name = %L);',
    n.name, n.description, n.favorite, n.tags, n.include_keywords, n.exclude_keywords, n.gender, n.name) as stmt
  from niches n where n.name like 'B92 %'
  union all
  select n.id * 1000 + row_number() over (partition by n.id order by nc.category_id), format(
    'insert into niche_categories (niche_id, category_id, include_children) '
    'select x.id, %L, %L from niches x where x.name = %L and x.owner_id = (select id from users order by id limit 1) '
    'on conflict do nothing;',
    nc.category_id, nc.include_children, n.name)
  from niches n join niche_categories nc on nc.niche_id = n.id where n.name like 'B92 %'
) s
union all
select 'commit;';
