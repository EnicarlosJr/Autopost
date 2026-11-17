# Autopost — ofertas de afiliado para grupos de WhatsApp

Cadastre um produto, gere a oferta no seu modelo de mensagem e envie aos grupos pelo WhatsApp Web que você já usa. Tudo roda no seu computador.

## Peças do sistema

| Peça | O que faz | Onde roda |
| --- | --- | --- |
| Painel (React) | Produtos, Fila e Configurações | `http://localhost:5173` (container `frontend`, nginx) |
| API (FastAPI) | Regras, login, imagens, fila | `http://localhost:8000` (`/docs` tem a documentação) |
| Worker e Beat (Celery) | Extração de lojas que permitem, agendamento, recuperação de travas, limpeza | containers `worker` e `scheduler` |
| PostgreSQL e Redis | Banco e fila de tarefas | containers `db` e `redis` |
| Extensão do Chrome | Lê produtos pelo seu navegador, cadastra direto da loja e envia pela sua aba do WhatsApp Web | pasta `extension` |

## Executar

Requer Docker Desktop.

```sh
docker compose up --build -d
```

Copie `.env.example` para `.env` e preencha antes da primeira execução. Para encerrar sem apagar dados: `docker compose down`. Evite `docker compose down -v`, que apaga banco, Redis e imagens.

**Onde guardar o projeto:** fora de pastas sincronizadas com a nuvem (OneDrive, Google Drive). O `.env` tem a senha do administrador e o segredo dos logins. Exemplo: `C:\dev\autopost`. Os dados ficam nos volumes do Docker; mover a pasta não os apaga, desde que o nome da pasta continue `autopost`.

O administrador inicial vem de `ADMIN_EMAIL` e `ADMIN_PASSWORD` do `.env` (usados só na primeira execução). Depois, troque a senha pelo botão **Trocar senha** no topo do painel. Trocar o `JWT_SECRET` encerra todos os logins abertos.

## Instalar a extensão (uma vez)

1. Abra `chrome://extensions` (ou `edge://extensions`) e ligue o **Modo do desenvolvedor**.
2. Clique em **Carregar sem compactação** e selecione a pasta `extension`.
3. Fixe o ícone do Autopost (raio azul) pelo ícone de quebra-cabeça da barra.
4. Abra o painel, faça login e deixe o WhatsApp Web aberto numa aba do mesmo Chrome.

Depois de atualizar os arquivos da extensão, clique em **Recarregar** no cartão dela em `chrome://extensions` e aperte F5 no painel. As opções da extensão (botão direito no ícone > Opções) mostram o intervalo entre mensagens e o envio automático.

## Fluxo do dia a dia

1. **Cadastrar:** na página do produto, clique no raio, cole o link de afiliado, confira o grupo e clique em **Cadastrar e pôr na fila** (ou **Só cadastrar**). Também dá para colar os links em Produtos.
2. **Mercado Livre:** a loja bloqueia acessos do servidor, então esses produtos ficam como "Aguardando navegador" e a extensão lê nome, imagem, preço, preço anterior e a condição ("no Pix") pelo seu navegador. Outras lojas são extraídas pelo servidor.
3. **Fila:** abas Aguardando aprovação, Prontas, Agendadas, Falhas, Enviadas e Canceladas. Com "Exigir aprovação" desligado, as publicações já entram em Prontas.
4. **Enviar:** em Prontas, **Enviar agora**, **Enviar fila agora** ou ligue o **Envio automático**, que envia mesmo com o painel fechado (precisa do Chrome aberto com o WhatsApp Web). A mensagem vai só como texto, sem foto, colada na conversa como um Ctrl+V. Assim o WhatsApp aplica a formatação do modelo (`*negrito*`, `_itálico_`, `~riscado~`) e monta a prévia do link sozinho.
5. **Preço conferido:** se o preço foi lido há mais de `PRICE_MAX_AGE_HOURS` (padrão 6 h), a extensão relê a loja antes de enviar. Mensagens no texto padrão recebem o preço novo; mensagens editadas à mão vão para Falhas com o aviso de que o preço mudou.

Regras que valem sempre:

- Nada é inventado: linhas sem dado (por exemplo, sem preço anterior) somem da mensagem.
- Uma publicação ativa por produto e grupo; repost no mesmo grupo só depois de `REPOST_WINDOW_HOURS` (padrão 24 h), a menos que você marque "repostar mesmo assim".
- O envio reserva a publicação antes de mandar (não sai duas vezes), confere o nome do grupo no topo da conversa e espera no mínimo 20 s entre mensagens.
- Preços lidos pelo navegador nunca são apagados por um reprocessamento no servidor.

Automatizar o WhatsApp Web não é um uso previsto pelo WhatsApp e pode levar a restrições no número. Prefira um número dedicado e intervalos generosos.

## Buscas automáticas (Mercado Livre)

Em **Buscas**, crie buscas salvas para o seu nicho: termos (um por linha), palavras proibidas no título, faixa de preço, desconto mínimo, nota mínima, frete grátis, frequência e grupo de destino.

1. **A extensão busca pelo seu Chrome.** A cada 30 s ela pergunta ao Autopost se alguma busca está na hora, abre a página de resultados numa aba em segundo plano, lê os anúncios (os patrocinados ficam de fora) e devolve. Termos da mesma busca são lidos com pausas de alguns segundos. Se o Mercado Livre pedir verificação, a busca para e o aviso aparece em Buscas.
2. **Achados.** Cada anúncio recebe uma nota de 0 a 100 (desconto, menor preço dos últimos 30 dias, avaliação, vendas e frete). Os que passam nos filtros aparecem em **Achados**, da melhor nota para a pior. Os demais ficam na aba "Fora dos filtros", com o motivo.
3. **Aprovar.** Escolha um horário ou deixe o sistema distribuir nos próximos horários livres do grupo. **Aceitar todos** aprova a lista inteira de uma vez. Descartados não voltam a aparecer.
4. **Modo automático.** Na busca, escolha "Agendar automaticamente os melhores": a cada execução, os melhores achados (até o limite definido) são agendados sem passar pela sua aprovação.
5. **Agenda dos grupos.** Em Buscas, defina por grupo o horário de postagem, o máximo por dia, o intervalo entre posts e depois de quantos dias o mesmo produto pode voltar.
6. **Link de afiliado.** Logo antes de cada envio, a extensão abre o anúncio no seu Chrome, clica em **Compartilhar** (barra de afiliados do Mercado Livre) e usa o `meli.la` gerado, já com o preço conferido. Para isso, o Chrome precisa estar logado na sua conta de afiliado. Sem o link, a publicação vai para Falhas com o motivo.

O histórico de preço de cada anúncio fica guardado. Use o fuso de `APP_TIMEZONE` (padrão `America/Sao_Paulo`) para os horários da agenda.

## Meu perfil: categorias oficiais e nichos

- **Categorias do Mercado Livre:** catálogo oficial (cerca de 12 mil categorias), com nomes e IDs exatamente como a API informa. Clique em **Atualizar categorias do Mercado Livre**: o servidor tenta baixar direto e, se o Mercado Livre bloquear, a extensão baixa pelo seu Chrome (cerca de 30 MB). O servidor também tenta atualizar sozinho toda segunda de manhã. Categorias que somem da API ficam inativas, nada é apagado.
- **Árvore:** expandir e recolher, pesquisa instantânea por nome ou ID, caminho completo, indicação de categoria final e estrela de favorita.
- **Nichos:** conjuntos reutilizáveis com categorias oficiais (com ou sem subcategorias), tags pessoais e palavras-chave incluídas e excluídas. Criar, editar, duplicar, excluir e favoritar. Cada nicho e cada favorita pertencem ao usuário logado; outro usuário não os vê.
- **Separação:** categoria oficial (ID do Mercado Livre), tag pessoal e nicho são coisas diferentes. Uma tag nunca é tratada como categoria.

## Campanhas

Em **Campanhas > Nova campanha**, um assistente em sete etapas monta a divulgação. Nada é enviado antes da confirmação na revisão.

1. **Informações:** nome da campanha. Ao avançar, ela é salva como rascunho para receber buscas e produtos.
2. **Nichos e categorias:** aplique nichos salvos em **Meu perfil** (as categorias e palavras são copiadas para a campanha; editar aqui não altera o nicho), ajuste as categorias oficiais do Mercado Livre na árvore e as palavras-chave e palavras excluídas.
3. **Busca de produtos:** "Buscar produtos" cria uma busca da campanha que a extensão executa no seu Chrome. Cada resultado é classificado na categoria oficial e filtrado pelas categorias, palavras excluídas, preço, desconto, nota e frete grátis. O histórico mostra cada busca (na fila, buscando, concluída, sem resultados, falhou) com "Ver resultados", "Repetir" e "Usar parâmetros". Nos resultados, selecione e clique em "Adicionar à campanha"; "Mostrar fora dos filtros" exibe o motivo de cada recusa. Em **Público** (Todos, Masculino ou Feminino), cada palavra é buscada com "masculino" ou "feminino" e anúncios do outro público ficam de fora (unissex continua valendo); o modo estrito aceita só anúncios que dizem o público no título. O nicho também guarda o público e o aplica na busca. Em **Confiabilidade**, "Básica" (padrão) exige pelo menos 50 vendidos, nota 4 ou mais e descarta títulos com termos como "banhado", "réplica" ou "1ª linha"; "Alta" exige 500 vendidos, nota 4,5 e só aceita loja oficial ou Full. Os resultados mostram os selos "Loja oficial" e "Full".
4. **Seleção dos produtos:** lista os produtos da campanha, com remoção em massa. Também dá para trazer produtos da tela **Produtos** ("Adicionar a uma campanha").
5. **Grupos de destino:** aplique um conjunto de grupos com um clique (ou salve a seleção como conjunto), defina o limite por grupo e a estratégia:
   - *Equilibrada:* cada produto vai para um grupo, alternando;
   - *Sequencial:* cada produto vai para todos os grupos;
   - *Por categoria:* usa as categorias oficiais do Mercado Livre (e as antigas, se houver) do cadastro de cada grupo;
   - *Personalizada:* você escolhe, para cada grupo, quais categorias oficiais da campanha ele recebe.
6. **Regras de automação:**
   - anúncios por execução e intervalo entre as mensagens da mesma execução (mínimo 20 s);
   - intervalo entre execuções (fixo ou variável);
   - data de início e de término, janela diária e dias da semana;
   - limite por dia (total e por grupo), pausas a cada N anúncios;
   - reutilizar o mesmo produto no mesmo grupo só depois de N dias (vazio usa o prazo do cadastro do grupo).

   Configurações impossíveis são recusadas, e a prévia avisa quando nem todos os anúncios cabem até a data de término.
7. **Revisão:** nichos, categorias oficiais, produtos na campanha e usados, anúncios por grupo, início e término previstos.

Campanhas criadas antes desta versão continuam funcionando com os filtros antigos de categoria e tags enquanto não tiverem produtos adicionados. Cada campanha pertence ao perfil que a criou.

Status no painel: *Rascunho*, *Aguardando execução* (agendada, nada enviado ainda), *Em execução*, *Pausada*, *Concluída*, *Concluída com falhas*, *Falhou* e *Cancelada*.

Ao confirmar, a campanha vira publicações agendadas comuns e sai pela mesma fila e extensão. Um produto nunca vai duas vezes para o mesmo grupo na mesma campanha, e a janela de repostagem de cada grupo é respeitada. **Pausar** segura o que ainda não saiu; **Retomar** replaneja a partir de agora sem repetir o que já foi enviado; **Cancelar** remove o restante da fila; **Duplicar** cria um rascunho igual. Cada campanha mostra progresso, falhas e o histórico de publicações.

Os achados aprovados recebem a categoria oficial identificada pelo Mercado Livre e o termo da busca como tag.

## Grupos

Em **Grupos**, cadastre os grupos pelo nome exato do WhatsApp, defina as categorias oficiais do Mercado Livre que cada um recebe (usadas na distribuição por categoria), o horário, o limite por dia e o prazo para repostar. Grupos inativos não aparecem nas campanhas.

**Conjuntos de grupos:** selecione grupos na lista e use "Salvar como conjunto" (ex.: "Floripa"). Na campanha, um clique no conjunto adiciona todos os grupos dele. Cada perfil tem os próprios conjuntos.

## Modelo da mensagem

Em **Configurações**, edite o texto da oferta com variáveis e veja a prévia ao vivo. Variáveis de linha (a linha some se faltar o dado): `{titulo}`, `{preco_de}`, `{preco_por}`, `{link}`, `{loja}`, `{categoria}`. Variáveis opcionais (somem sem apagar a linha): `{condicao}` (" no Pix"), `{desconto}` (" (44% OFF)"), `{desconto_pct}` ("44"). **Restaurar modelo padrão** volta ao texto original.

## Testes

```sh
docker compose exec api pytest -q          # backend (74 testes)
pip install playwright pytest && playwright install chromium
pytest tests_e2e                            # extensão: leitura de preço, busca, link de afiliado e envio, com páginas simuladas
```

## API

REST em `/api`: `products` (inclui `/from-browser` e `/{id}/browser-data`), `publications` (inclui `/queue`, `/summary`, `/bulk/approve`, `/{id}/claim`, `/{id}/sent`, `/{id}/failed`), `automations/settings`, `searches` (inclui `/due`, `/{id}/run`, `/{id}/results`), `listings` (inclui `/approve`, `/accept-all`, `/discard`), `group-schedules`, `ml-categories` (inclui `/children`, `/search`, `/favorites`, `/sync`, `/import`), `niches`, `campaigns` (inclui `/options`, `/preview`, `/{id}/confirm`, `/pause`, `/resume`, `/cancel`, `/duplicate`), `automations/template-preview`, `automations/logs`, `auth/login`, `auth/password`. Listas aceitam `limit` e `offset` e devolvem o total no cabeçalho `X-Total-Count`.

Após 5 senhas erradas em 15 minutos para o mesmo e-mail e IP, o login fica bloqueado temporariamente. Tokens de usuários desativados deixam de valer na hora.
