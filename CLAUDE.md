# Autopost: contexto do projeto

> Contexto de trabalho para quem mexe no código (pessoas e Claude).
> **Pasta oficial:** `C:\Projetos\Autopost` (git, branch `main`, remoto `github.com/EnicarlosJr/Autopost`).
> A cópia em `OneDrive\Documentos\Autopost` é antiga (sem git, parada em 13/11) e não deve ser editada.
> Manual de uso: `README.md`. Plano de mudanças: `Roteiro de regularização do Autopost.pdf` (23/11/2026, Matheus Assis), hoje só na pasta do OneDrive.
> Atualizado em 23/11/2026, a partir do commit `21ceb07` (mais a melhoria da busca: parecidos e melhores).

## O que é

Sistema local de **ofertas de afiliado do Mercado Livre** para **grupos de WhatsApp**. Ele busca produtos, classifica na categoria oficial do ML, filtra e pontua, monta a mensagem a partir de um modelo, agenda por grupo e por campanha e envia pela aba do WhatsApp Web do próprio usuário, por meio de uma extensão do Chrome. Tudo roda no computador do usuário via Docker. Interface, textos, comentários e mensagens de erro são em **português do Brasil**.

Canais do usuário citados no roteiro: grupo(s) de WhatsApp, Instagram `@base92.achados` e uma landing page.

## Arquitetura

| Peça | Stack | Endereço / onde |
| --- | --- | --- |
| Painel | React 18 + TS + Vite + MUI 6 + Recharts, servido por nginx | `localhost:5173` (container `frontend`) |
| API | FastAPI + SQLAlchemy 2 + Alembic + Pydantic 2, JWT (PyJWT) + argon2, Pillow | `localhost:8000`, rotas em `/api`, docs em `/docs` |
| Worker / Beat | Celery 5 + Redis | containers `worker` e `scheduler` |
| Banco | PostgreSQL 16 | container `db`, volume `postgres_data` |
| Extensão | Chrome MV3, JS puro em módulos | pasta `extension/`, carregada sem compactação |

**Princípio central:** o servidor não envia nada ao WhatsApp e quase não lê o Mercado Livre, porque a loja bloqueia o servidor e **não libera busca pela API**. Quem age no navegador é sempre a extensão: ela pergunta à API o que fazer, executa na aba do usuário e devolve o resultado.

Tarefas do Beat (`workers/celery_app.py`, fuso `America/Sao_Paulo`): `publications.release_due` (a cada 30 s), `maintenance.recover_stuck` (a cada 120 s), `maintenance.cleanup_logs` (diária, 04:17) e `catalog.refresh` (segunda, 05:23, baixa a árvore de categorias do ML).

## Mapa do código

```
backend/app/
  main.py                 app FastAPI, CORS (painel + chrome-extension://), seed do admin e da "Regra principal"
  auth/                   login (bloqueio após 5 erros em 15 min), troca de senha
  core/                   deps (require_user), security (JWT/argon2), ratelimit
  models/                 Product, Publication, AutomationRule/Log, Search, Listing, PricePoint, GroupSchedule,
                          Campaign, CampaignSearch, CampaignSearchResult, CampaignProduct, GroupSet,
                          MlCategory, FavoriteCategory, Niche, NicheCategory, User
  catalog/                categorias oficiais do ML (~12 mil, árvore em api.mercadolibre.com/sites/MLB/categories/all),
                          favoritas e nichos por usuário
  products/               extractor (lojas que permitem servidor), image_fetch, images (rotas), media,
                          social_image.py (foto 1080x1080, corte de bordas, faixa de marca d'água), service, urls
  publications/           messages.py (modelo e variáveis), service.py, router.py (fila, claim/sent/failed)
  searches/               buscas salvas, achados (listings), agenda de grupos
  searches/ranking.py     puro, sem banco: nota da oferta (offer_score), agrupamento de parecidos
                          (same_product, group_offers) e escolha dos melhores com variedade (pick_best)
  campaigns/              service.py (filtros, distribuição, ritmo, plano), search_service.py (busca dentro
                          da campanha: extensão busca no site, classifica com domain_discovery, servidor filtra)
  automations/router.py   configurações, forma de envio avulsa, prévia do modelo, logs
  school_lists/           listas escolares: router.py (lista, itens, 3 opções por item, fila de conferência
                          /refresh/next, página page.html, /api/school-visitors), public.py (páginas sem login
                          /escolas/<escola>[/<série>]: identificação por nome do aluno + turma, cookie com token)
                          e service.py (puro: catálogo, totais, render_page, render_landing, slugs)
  workers/                celery_app.py, tasks.py
backend/migrations/versions/   0001 → 0019 (0011 catálogo, 0012–0013 busca e regras da campanha,
                               0014 público do nicho, 0015 confiabilidade, 0016–0017 forma de envio,
                               0018 produto de catálogo do anúncio, 0019 padrão do perfil: #publi, selo de desconto,
                               campanha personalizada, 0020 listas escolares,
                               0021 página pública e responsáveis)
backend/tests/                 pytest (README diz 74 testes); fixture HTML do ML
extension/
  background.js   service worker: recebe pedidos do painel, roda a fila automática e as buscas
  bridge.js       ponte painel (localhost:5173) ↔ extensão
  capture.js      abre a página do produto em aba de fundo e roda reader.js; também gera o meli.la
                  clicando em "Compartilhar" da barra de afiliados (com novas tentativas)
  reader.js       lê nome, imagem, preços e condição ("no Pix") da página do produto
  searcher.js / search_reader.js   buscas no site do ML (patrocinados de fora, selos loja oficial/Full)
  schoollists.js  reconfere o preço dos produtos das listas escolares (uma leitura a cada 2 min, sem gerar link)
  catalog.js      baixa o catálogo de categorias pelo Chrome quando o servidor é bloqueado
  publisher.js    envio: reserva (claim), confere preço se velho, ensureAffiliateLink, envia, registra
  whatsapp.js     todos os seletores do WhatsApp Web ficam em sendInWhatsApp: é o único lugar a ajustar.
                  Texto colado como Ctrl+V; foto colada como arquivo com legenda; dryRun = "Ensaiar"
  config.js       MIN_INTERVAL_SECONDS = 20 (trava entre quaisquer mensagens), sendIntervalSeconds = 60
frontend/src/
  pages/          Dashboard, Products, Queue, Settings, Searches, Listings, Campaigns, CampaignEditor
                  (assistente de 7 etapas), Groups, Profile (categorias e nichos), Login; rotas em NewApp.tsx
  components/     CampaignSearchPanel, CategoryTree, WhatsAppPreview, Ui,
                  Bulk (useSelection, SelectAll, SelectMatching, BulkBar, useConfirm, fetchAllIds, inBatches, eachItem),
                  Fields (GroupPicker, ProductPicker, SendModeFields: forma de envio + marca d'água + prévia da foto)
  services/       api.ts (axios), sender.ts (conversa com a extensão)
  labels.ts, campaignLabels.ts   rótulos em PT-BR dos status
tests_e2e/        Playwright com páginas simuladas do ML e do WhatsApp (7 testes)
```

## Conceitos e estados

- **Categoria oficial** (ID do ML), **tag pessoal** e **nicho** são coisas diferentes: uma tag nunca é tratada como categoria. Nichos, favoritas, campanhas e conjuntos de grupos pertencem ao usuário que os criou.
- **Nicho:** categorias oficiais (com ou sem subcategorias), tags, palavras incluídas e excluídas, público (todos/masculino/feminino). Aplicar um nicho na campanha **copia** os dados; editar na campanha não altera o nicho.
- **Confiabilidade da busca:** Básica (padrão: ≥ 50 vendidos, nota ≥ 4, sem "banhado", "réplica", "1ª linha") ou Alta (≥ 500 vendidos, nota ≥ 4,5, só loja oficial ou Full).
- **Nota da oferta (0–100, `ranking.offer_score`):** desconto até 40 (metade se o preço ficou parado ≥ 3 dias, variação < 5%), nota ponderada pelas vendas até 20 (referência 4,3 com peso 30), vendas até 15, menor preço em 30 dias 10, loja oficial 7, Full 5, frete grátis 3.
- **Parecidos (`ranking.same_product`):** mesmo produto de catálogo (`listings.catalog_product_id`, lido de `/p/MLB…`) ou títulos semelhantes (Jaccard ≥ 0,55, ou 80% do menor contido) na mesma categoria e com preço até 1,8x. Nunca junta medidas diferentes ("480gb" x "1tb"), modelos sem número em comum nem públicos diferentes. Representante do grupo: maior nota + bônus de até 8 para o mais barato.
- **Busca por nicho (`POST /campaigns/{id}/searches/by-niches`):** uma busca por nicho, com categorias, palavras, exclusões e público do nicho; os filtros enviados valem para todas, menos o público. Mais de 10 palavras vira mais de uma busca (`MAX_TERMS`).
- **Melhores N (`ranking.pick_best`, `POST /campaigns/{id}/searches/{sid}/best`):** um por grupo, sem grupos já na campanha; limita por categoria (~40% de N quando há várias) e por loja (2), com penalidade para títulos parecidos com os já escolhidos; se os limites travarem, completa sem eles.
- **Estilo da publicação (`Publication.style()`):** forma de envio = da publicação, senão da campanha, senão do perfil. Modelo da mensagem e marca d'água = da campanha se `campaigns.custom_style`, senão do perfil (`publications.service.template_for`). #publi e selo de desconto (`show_discount`) = sempre do perfil. Ao mudar o preço, cada publicação é comparada com o texto padrão do seu próprio modelo (`products.service._standard_texts`).
- **Perfil = `automation_rules` (linha única).** Editado em Meu perfil > Mensagem e foto (`StyleSettings.tsx`, `TemplateEditor.tsx`); Configurações ficou só com a automação dos produtos e o histórico.
- **Foto (`social_image.compose`):** desenhada em 2x e reduzida (bordas suaves); selo #publi no canto superior esquerdo, selo de desconto (≥ 5%) no superior direito, faixa no rodapé com grupo à esquerda e Instagram à direita (fonte encolhe para caber); com selo, o topo ganha respiro. Cache em disco com chave `v2|…`.
- **Forma de envio** (`send_mode`): `preview` (só texto; o WhatsApp monta o cartão do link) ou foto + texto (imagem 1080x1080 com legenda e marca d'água opcional). Definida por campanha, pelas Configurações para ofertas avulsas, e por publicação (`send_mode_choice`) na Fila.
- **Produto:** `pending` → `processed` | `needs_review` | `awaiting_browser` (ML: a extensão completa os dados).
- **Publicação, ativos:** `pending`, `awaiting_approval`, `approved` (Prontas), `scheduled`, `sending`, `paused`. **Finais:** `sent`, `failed`, `cancelled`.
- **Busca da campanha:** `queued` → buscando → concluída / sem resultados / falhou (com lease de 10 min, até 10 termos).
- **Campanha no painel:** Rascunho, Aguardando execução, Em execução, Pausada, Concluída, Concluída com falhas, Falhou, Cancelada. Ao confirmar, ela vira publicações agendadas comuns.

## Regras que o código garante (não quebrar)

1. **Nada é inventado:** linha do modelo sem dado some da mensagem.
2. **Uma publicação ativa por produto e grupo.** Repost só após `REPOST_WINDOW_HOURS` (24 h) ou com "repostar mesmo assim". A campanha nunca manda o mesmo produto duas vezes ao mesmo grupo e respeita o prazo de reuso (da campanha ou do grupo).
3. **Envio com reserva** (`/publications/{id}/claim`): nunca sai duas vezes. Confere o nome do grupo no topo da conversa. Mínimo de 20 s entre quaisquer mensagens.
4. **Preço conferido:** se a leitura tem mais de `PRICE_MAX_AGE_HOURS` (6 h), a extensão relê antes de enviar. Texto padrão é atualizado; texto editado à mão vai para Falhas.
5. **Preço lido pelo navegador nunca é sobrescrito** por reprocessamento no servidor.
6. Sem link de afiliado, a publicação vai para Falhas com o motivo.
7. Configurações impossíveis de campanha são recusadas, nunca "consertadas" em silêncio.
8. Categorias que somem da API do ML ficam inativas; nada é apagado.
9. Agrupar e "escolher os melhores" só sugerem: nada entra na campanha sem o clique em "Adicionar à campanha".
10. **#publi sempre:** a identificação de publicidade do perfil (`automation_rules.disclosure_text`, precisa conter "publi") vai na primeira linha do texto enviado (`Publication.outgoing_message` = `messages.with_disclosure`) e no selo da foto. Não é guardada em `publication.message` (o `normalize_offer_text` antigo ainda tira "#publi" do topo do texto salvo); a extensão envia `outgoing_message`. Campanha não remove.

## Configuração e comandos

`.env` (modelo em `.env.example`): `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` (só na primeira execução), `POSTGRES_PASSWORD` (só na criação do volume), `REPOST_WINDOW_HOURS`, `PRICE_MAX_AGE_HOURS`, `LOG_RETENTION_DAYS`, `VITE_API_URL`. Nunca colar valores do `.env` em conversas ou commits (já está no `.gitignore`).

```sh
docker compose up --build -d          # subir
docker compose down                   # parar sem perder dados (NUNCA -v)
docker compose exec api pytest -q     # testes do backend
pytest tests_e2e                      # extensão (precisa de playwright + chromium)
```
- Depois de mudar a extensão: subir a `version` no `manifest.json`, Recarregar em `chrome://extensions` e F5 no painel.
- Envio automático com a janela coberta: abrir o Chrome com `--disable-backgrounding-occluded-windows` e não bloquear a tela.

## Rumo atual: roteiro de regularização

Princípio: o sistema continua fazendo o trabalho pesado, mas **deixa de agir sozinho no gerador de link do ML e no WhatsApp Web**, que proíbem automação. Nesses dois, a automação prepara e o usuário dá **um clique por lote**. Onde há caminho oficial (API da Shopee, bot do Telegram, API da Amazon), segue 100% automático. Meta: 10 a 15 min/dia do usuário.

| Ordem | Fase | O que muda | Esforço |
| --- | --- | --- | --- |
| hoje | **0. Sem código** | cadastrar mídias no painel de afiliado do ML; 2º admin no grupo; ler Termos (cláusulas 1.8, 4.3, 4.4); mensagem fixa de regras no grupo; landing sem cara de canal oficial | < 1 h |
| sem. 1 | **1. Mensagem, filtros, ritmo** | linha fixa "#publi \| link de afiliado" (por campanha, nunca removível); preço reconferido até 30 min antes, produto esgotado cancela; rodapé "Preço e estoque podem mudar" com horário; palavras bloqueadas no título. Filtros (`campaigns/search_service.py`, `searches/service.py`): só novos, reputação mínima do vendedor (padrão verde), só página de anúncio. Ritmo (`publisher.js`, regras da campanha): ≥ 15 min entre mensagens com variação aleatória, teto de 20/dia por grupo, janela 8h–22h, abertura variada | 2–3 dias |
| sem. 2 | **3. Telegram + liberação no WhatsApp** | destino "Telegram" (token do bot + ID do canal) nas campanhas; `whatsapp.js` em modo "liberação": cola mensagem/foto e **para no botão enviar**; painel "Prontas para enviar" para liberar em lote. Migração: Telegram recebe tudo, WhatsApp recebe uma seleção | 4–6 dias |
| sem. 3 | **2. Links do ML em lote** | status "Aguardando link" e tela "Gerar links do dia" com contador ("12 de 20"); `capture.js` deixa de clicar no gerador (só lê o link após o clique do usuário); `publisher.js` deixa de chamar `ensureAffiliateLink` no envio. Busca: avaliar API oficial do ML ou ler só durante a tela de links. `meli.la` sem encurtador nem parâmetro extra | 3–4 dias |
| sem. 4+ | **4. Conectores de loja** | tabela `stores` e campo `store` em produtos, ofertas e campanhas; interface por loja `search()`, `make_link()`, `rules()`; Shopee (Open API GraphQL, `sub_id` por campanha), Amazon (API de associados após as primeiras vendas), Magalu (lote, como o ML); credenciais só no `.env` do servidor, nunca na extensão | 1 sem. + 2–3 dias/loja |
| sem. 4+ | **5. Monitoramento** | painel por canal e loja (envios, cliques por `sub_id`/UTM, entradas); alertas de restrição, sessão caída e saídas em massa; lembrete semanal de comissões anuladas; registro de cada envio (data, canal, link, preço); **não guardar telefones de membros** (LGPD; a página das listas escolares guarda só nome do aluno + turma, com autorização); número reserva como admin | 2–3 dias |

O que já existe e ajuda no roteiro:
- **Foto + texto** e **marca d'água** já estão prontos (0016/0017, `social_image.py`), então o modo "liberação" pode colar a foto também.
- **"Ensaiar no WhatsApp"** (`dryRun` em `whatsapp.js`) já abre o grupo, cola, confere e apaga: é a base natural do modo liberação (parar antes de enviar em vez de apagar).
- Campanhas já têm janela diária, limite por dia e por grupo, intervalo variável e mínimo de 20 s; a Fase 1 sobe esses mínimos e acrescenta variação no texto.
- O filtro de confiabilidade já cobre parte da "reputação do vendedor" da Fase 1 (vendidos, nota, loja oficial/Full), mas ainda não lê a cor da reputação nem a condição novo/usado.

Duplicação conhecida: há dois sistemas de busca, as Buscas automáticas (tela Buscas, com filtros próprios e sem categorias oficiais, confiabilidade e público) e a busca dentro da campanha. Unificar (por exemplo, a busca automática usando nicho e os mesmos filtros) é um candidato natural.

Próximos passos possíveis na busca: levar o agrupamento e os "melhores" para a tela Achados (buscas automáticas), ler a reputação do vendedor e a condição novo/usado (Fase 1), e usar as páginas "Mais vendidos" e "Ofertas do dia" como fonte.

Cuidados: o roteiro se baseia em resumos de terceiros dos Termos do ML, então o texto oficial deve ser conferido antes da Fase 2 (não é orientação jurídica). Envio 100% automático no WhatsApp continua fora das regras; se for mantido, usar o ritmo da Fase 1 e deixar só admins postando no grupo.

## Convenções

- Textos de interface, erros e comentários em PT-BR, frases curtas e diretas.
- Toda mudança de schema vem com migração Alembic numerada (próxima: `0022_…`), idempotente (checa colunas com `inspect`, como as atuais).
- Listas da API aceitam `limit`/`offset` e devolvem `X-Total-Count`.
- Seletores do WhatsApp só em `whatsapp.js > sendInWhatsApp`; leitura de página só em `reader.js`/`search_reader.js`.
- Ao mudar regra de negócio: atualizar o teste correspondente e o README.
- Listas: toda lista tem seleção (`useSelection` ou estado local), `SelectAll` da página, `SelectMatching` quando é paginada (usa `fetchAllIds` com os mesmos filtros) e `BulkBar` com as ações. Rotas em massa aceitam até 200 ids: chame com `inBatches`; rotas sem versão em massa, com `eachItem`.
- Confirmações sempre com `useConfirm` (nunca `window.confirm`), com o texto do botão dizendo o que acontece.
- Campo de grupo do WhatsApp: sempre `GroupPicker` (grupos cadastrados + nome livre). Produto: `ProductPicker` (busca no servidor). Forma de envio: `SendModeFields`.
- A loja do produto (`marketplace`) vem do link (`products/sources.marketplace_of`); o formulário não pede.
- Exclusões: publicações só canceladas ou com falha (enviadas contam para a repostagem); buscas da campanha em andamento não são apagadas.
- Verificar o painel sem `node_modules`: `tsc` com stubs de `@mui/material`, `react-router-dom`, `axios` e `react` pega erros de sintaxe e de tipos do próprio projeto.
- Commits pequenos e descritivos (em inglês, como os atuais), na `main`.
