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

1. **Cadastrar:** na página do produto, clique no raio, cole o link de afiliado, confira o grupo e clique em **Cadastrar e pôr na fila** (ou **Só cadastrar**). Também dá para colar os links em Produtos. A loja (Mercado Livre, Amazon, Magalu, Shopee) é identificada pelo link.
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
2. **Achados.** Cada anúncio recebe uma nota de 0 a 100: desconto (vale metade se o preço ficou parado por dias, sinal de "de/por" inflado), nota ponderada pelas vendas (um 5,0 com poucas vendas vale menos que um 4,8 com milhares), vendas, menor preço dos últimos 30 dias, loja oficial, Full e frete grátis. Os que passam nos filtros aparecem em **Achados**, da melhor nota para a pior. Os demais ficam na aba "Fora dos filtros", com o motivo.
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
2. **Nichos e categorias:** marque os nichos salvos em **Meu perfil** (as categorias são copiadas para a campanha; as palavras-chave ficam no nicho e são usadas na busca por nicho; editar aqui não altera o nicho), ajuste as categorias oficiais do Mercado Livre na árvore e as palavras-chave e palavras excluídas.
3. **Busca de produtos:** "Buscar produtos" cria uma busca da campanha que a extensão executa no seu Chrome. Cada resultado é classificado na categoria oficial e filtrado pelas categorias, palavras excluídas, preço, desconto, nota e frete grátis. O histórico mostra cada busca (na fila, buscando, concluída, sem resultados, falhou) com "Ver resultados", "Repetir" e "Usar parâmetros". Nos resultados, selecione e clique em "Adicionar à campanha"; "Mostrar fora dos filtros" exibe o motivo de cada recusa. Em **Público** (Todos, Masculino ou Feminino), cada palavra é buscada com "masculino" ou "feminino" e anúncios do outro público ficam de fora (unissex continua valendo); o modo estrito aceita só anúncios que dizem o público no título. O nicho também guarda o público e o aplica na busca. Em **Confiabilidade**, "Básica" (padrão) exige pelo menos 50 vendidos, nota 4 ou mais e descarta títulos com termos como "banhado", "réplica" ou "1ª linha"; "Alta" exige 500 vendidos, nota 4,5 e só aceita loja oficial ou Full. Os resultados mostram os selos "Loja oficial" e "Full".

   **Parecidos agrupados.** O mesmo produto vendido por lojas diferentes, em outra cor ou com título quase igual vira um grupo: aparece só o melhor (maior nota, com preferência pelo mais barato), com "+N parecidos" para abrir o grupo e o selo "Menor preço entre os parecidos". O agrupamento usa o produto de catálogo do Mercado Livre quando a página informa e, além disso, as palavras do título, a categoria e o preço. Medidas diferentes ("480 GB" x "1 TB"), modelos diferentes e públicos diferentes (masculino x feminino) nunca se juntam. Anúncios parecidos com algo que já está na campanha recebem o aviso "Parecido com um já na campanha". O interruptor "Agrupar parecidos" mostra a lista completa.

   **Escolher os melhores.** Informe quantos e clique em "Escolher os melhores": o sistema marca um por grupo de parecidos, pula o que já está na campanha (ou é parecido com algo dela) e varia categoria (cerca de 40% no máximo por categoria quando há várias) e loja (até 2 por loja). Se esses limites impedirem de chegar ao número pedido, ele completa sem eles. Nada é adicionado sozinho: confira e clique em "Adicionar à campanha".
   **Buscar pelos nichos.** Na etapa 3 aparecem todos os nichos do perfil; marque os que quiser (ou "Marcar todos") e clique em "Buscar nos N nichos marcados": é criada uma busca para cada nicho, cada uma com as palavras, categorias, exclusões e o público do próprio nicho (um nicho masculino busca "masculino"; um de ferramentas, não). Os filtros de preço, desconto e confiabilidade da tela valem para todas. Nicho com mais de 10 palavras vira mais de uma busca. A busca manual também pode ser preenchida com um nicho só. Cada nicho leva cerca de 1,5 min; o histórico se atualiza sozinho e mostra quantas faltam. Excluir buscas concluídas pede confirmação e avisa quantos resultados serão apagados.
   **Montar a campanha com os melhores.** Com buscas concluídas, informe quantos por busca e clique em "Adicionar até N": a campanha recebe os melhores de cada busca (mesma regra de "Escolher os melhores"), sem repetir produto entre as buscas.

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
7. **Revisão:** nichos, categorias oficiais, produtos na campanha e usados, anúncios por grupo, início e término previstos. Se a campanha programar num dia mais anúncios para um grupo do que o limite diário do cadastro dele (em **Grupos**), aparece um aviso com o botão "Respeitar o limite do grupo", que preenche "Limite por grupo por dia".
   Na etapa 5, um grupo desligado em **Grupos** aparece com o botão "Ativar e usar". Na etapa 6, "Espalhar" calcula o intervalo para distribuir os anúncios na janela do dia (com variação de cerca de 20%).
   Na tela **Produtos**, "Ordenar: Maior desconto" e "Selecionar os N de maior desconto" (só prontos, com os filtros atuais) ajudam a escolher; "Adicionar a uma campanha" deixa criar uma campanha nova ou juntar a um rascunho ou campanha pausada.

Campanhas criadas antes desta versão continuam funcionando com os filtros antigos de categoria e tags enquanto não tiverem produtos adicionados. Cada campanha pertence ao perfil que a criou.

Status no painel: *Rascunho*, *Aguardando execução* (agendada, nada enviado ainda), *Em execução*, *Pausada*, *Concluída*, *Concluída com falhas*, *Falhou* e *Cancelada*.

Ao confirmar, a campanha vira publicações agendadas comuns e sai pela mesma fila e extensão. Um produto nunca vai duas vezes para o mesmo grupo na mesma campanha, e a janela de repostagem de cada grupo é respeitada. **Pausar** segura o que ainda não saiu; **Retomar** replaneja a partir de agora sem repetir o que já foi enviado; **Cancelar** remove o restante da fila; **Duplicar** cria um rascunho igual. Cada campanha mostra progresso, falhas e o histórico de publicações.

Os achados aprovados recebem a categoria oficial identificada pelo Mercado Livre e o termo da busca como tag.

## Listas escolares (orçamento para os pais)

Menu **Publicar > Listas escolares**. Cada lista é a lista de material de uma série (ex.: Maternal II 2027), dividida em **Coletivo** (vai para a escola) e **Individual**.

1. **Nova lista**: escola, série e ano.
2. **Adicionar itens**: cole a lista da escola, um item por linha. `2 Colas brancas 90 g` ou `Folhas de ofício | 500 folhas` (o que vem depois do `|` ou o número do começo vira "como a escola pede").
3. **Escolha até 3 produtos por item** (por padrão Econômica, Equilibrada e Premium; o nome é editável). Cole o link do anúncio: o Autopost cadastra o produto e a extensão lê nome, foto e preço no seu Chrome. Em **Qtd.** vai quanto o pai precisa comprar daquele anúncio (ex.: 2 pacotes).
   - Prefira a **página de catálogo** (`/p/MLB…`): ela é a mesma para todos os vendedores do produto e o Mercado Livre mostra nela a melhor oferta do momento. Assim o preço conferido é sempre o do **mesmo produto** em promoção, e o link continua valendo quando o vendedor mais barato muda. Anúncio avulso (sem `/p/`) aparece como "Anúncio avulso": só aquele anúncio é acompanhado.
   - **Equivalentes no Mercado Livre**: ao salvar um produto, a extensão procura o **mesmo produto** em outras ofertas e marcas (3 páginas: o item pela relevância, o item do mais barato para o mais caro e o produto escolhido). Cada anúncio é conferido contra o item: mesma medida (folhas, g, ml, cores, cm, nº), mesma cor, unidade e não kit, mesma variação (espiral x brochura, líquida x bastão...), não acessório ("capa para caderno"), sem termos de baixa confiabilidade, nota ≥ 4 e ≥ 10 vendidos. Na dúvida, fica de fora; o painel mostra quantos foram recusados e por quê.
   - As sugestões aparecem embaixo do item, por opção vazia: **Econômica** (a mais barata, abaixo das que você já tem), **Premium** (loja oficial, nota ≥ 4,6 ou muito vendido) e **Equilibrada** (melhor nota pelo preço). Com as 3 preenchidas, aparece **Mais barato que as opções atuais** quando houver um ao menos 3% mais barato. **Usar** preenche a opção e gera o link de afiliado; **Descartar** some com o anúncio nas próximas buscas. Nada entra sozinho. **Buscar de novo** refaz a busca.
4. **Conferência automática**: com o Chrome aberto, a extensão relê um produto por vez (no máximo um a cada 2 min, quando não há envio nem busca) sempre que o preço tiver mais de 12 h (ajustável por lista). Só lê a página e confere se o meli.la ainda abre o produto; não gera link. **Atualizar todos os preços** faz a leitura de todos na hora.
   - **Nada sai da lista sozinho.** Se a leitura falha, o último preço continua e a próxima tentativa espera 2 h. Se o Mercado Livre diz que acabou ou pausou, a opção fica marcada "Indisponível no ML", sai da página dos pais até voltar (o item continua) e o Autopost busca um substituto.
   - **Pix e Mercado Pago:** o ML destaca o preço no Pix ("R$ 4.435 no Pix, ou R$ 4.580 em 10x sem juros"). O Autopost guarda os dois: a página dos pais soma o **preço no cartão** e mostra o desconto em verde ("R$ 4.435 no Pix"), para o carrinho nunca ficar mais caro que a página. Condições vistas perto do preço (Pix, Mercado Pago, cupom, Meli+) aparecem no painel.
5. **Link de afiliado**: ao salvar um link ou usar uma sugestão, o painel lê o produto e já gera o meli.la (um clique seu). Opções sem link ou com link que não abriu na última conferência aparecem no aviso da lista; **Gerar links que faltam** gera todos em lote. Na página dos pais, opção sem link (ou com link quebrado) usa o link comum, sem comissão, para nunca levar a uma página com erro.
6. **Baixar página de orçamento**: um arquivo `.html` único (sem dependências) para publicar no seu site ou landing. Os pais escolhem a opção de cada item, ajustam a quantidade, marcam o que já têm ("Já tenho"), veem o total e abrem cada item no Mercado Livre (o ML não deixa encher o carrinho de uma vez; cada item tem o botão "Pus no carrinho"). A página mostra o horário da conferência mais antiga e o aviso #publi do seu perfil. Gere de novo depois de atualizar os preços.

7. **Página online para os pais** (cartão "Página online para os pais" na lista): ligue **Publicada**, informe as **turmas** da série (ex.: A, B, C) e um **contato** para os pais. O link para mandar no grupo é `APP_PUBLIC_URL/escolas/<escola>` (ex.: `/escolas/colegio-cpcm`), um por escola.
   - O responsável informa **só o nome do aluno e a turma**, marca a autorização e vai direto para a lista da série, com os preços da última conferência (a página é montada na hora, não precisa baixar nem subir arquivo).
   - O navegador guarda um cookie (só um token, por 1 ano): quem já se identificou entra direto. "trocar aluno" volta ao formulário (irmãos em outra série).
   - Cada identificação fica em **Listas escolares › Responsáveis**: aluno, turma, escola, número de acessos (um por meia hora), primeiro e último acesso. Dá para filtrar, exportar CSV e excluir (pedido de exclusão do responsável). Nada de telefone ou e-mail é coletado.
   - Até 20 identificações por IP a cada 15 min (contra robôs).
   - **Online de verdade:** as páginas são servidas pela API (porta 8000), em `/escolas/...`, sem login. Para os pais abrirem de fora, a API precisa estar acessível na internet (servidor/VPS ou um túnel, como o Cloudflare Tunnel) e o `.env` precisa de `APP_PUBLIC_URL` com o endereço público (vale também para as fotos). Exponha só o caminho `/escolas/` se puder; o painel e a `/api` continuam protegidos por login, mas não precisam ficar abertos.
   - Dados de criança: o nome do aluno é dado pessoal de menor (LGPD, art. 14). O formulário pede a autorização do responsável e mostra o contato para exclusão; confira o texto com a escola antes de divulgar.

Produto de lista escolar não vira publicação automática; para ofertá-lo no grupo, use Campanhas ou a Fila como qualquer produto.

## Forma de envio: prévia do link ou foto + texto

Cada campanha escolhe, em **Regras de automação > Forma de envio**:

- **Texto com prévia do link:** envia só o texto; o WhatsApp monta o cartão com foto e título do link.
- **Foto + texto:** envia a foto do produto com a mensagem como legenda. A foto vem na maior qualidade que o Mercado Livre oferece, tem as bordas brancas cortadas e é padronizada em 1080 x 1080, então todas ficam do mesmo tamanho. Ela leva o selo **#publi** no canto superior esquerdo, o selo de desconto ("-30% OFF") no canto superior direito quando o produto tem preço anterior, e a faixa no rodapé com o nome do grupo e o Instagram (marca d'água).

**Padrão do perfil e personalização.** Em **Meu perfil > Mensagem e foto** ficam o modelo da mensagem, a identificação de publicidade, a marca d'água, o selo de desconto e a forma de envio das ofertas avulsas. Cada campanha usa esse padrão, a menos que você desligue **Usar o padrão do perfil** em **Regras de automação > Mensagem e foto** e defina a mensagem e a marca d'água só daquela campanha (elas começam com o que está no perfil).

**#publi.** O programa de afiliados pede que o afiliado se identifique. A identificação (padrão "#publi"; pode ser, por exemplo, "#publi | link de afiliado", mas precisa ter #publi) vai na primeira linha de toda mensagem e no selo da foto. Ela não fica guardada no texto da publicação: é acrescentada no envio, então editar a mensagem à mão não a remove, e campanha nenhuma consegue tirá-la. A prévia da Fila mostra o texto exatamente como sai.

As **ofertas avulsas** (fora de campanha: aprovadas em Achados, criadas na Fila ou geradas pelos Produtos) usam a forma de envio e a marca d'água do perfil. Para trocar só uma publicação, use **Editar** na Fila e escolha a forma de envio (Padrão, Texto com prévia do link ou Foto + texto).

Para conferir antes, use **Ensaiar no WhatsApp** na **Fila**: a extensão abre o grupo, cola a mensagem (ou a foto com legenda), confere e apaga, sem enviar nada.

## Envio automático: janela coberta

O Chrome "congela" páginas que não estão visíveis. Quando a janela do WhatsApp fica minimizada, coberta por outro programa ou com a tela bloqueada, o WhatsApp não processa o texto colado nem monta a prévia. A extensão traz a janela para a frente antes de cada envio, mas o Windows às vezes não deixa.

Para o Chrome tratar a janela como visível mesmo coberta, abra o Chrome por um atalho com `--disable-backgrounding-occluded-windows` no fim do campo **Destino** (Propriedades do atalho). Deixe a tela sem bloquear enquanto houver campanha rodando.

## Grupos

Em **Grupos**, cadastre os grupos pelo nome exato do WhatsApp, defina as categorias oficiais do Mercado Livre que cada um recebe (usadas na distribuição por categoria), o horário, o limite por dia e o prazo para repostar. Grupos inativos não aparecem nas campanhas.

**Conjuntos de grupos:** selecione grupos na lista e use "Salvar como conjunto" (ex.: "Floripa"). Na campanha, um clique no conjunto adiciona todos os grupos dele. Cada perfil tem os próprios conjuntos.

## Ações em massa

Todas as listas têm caixa de seleção, "Selecionar todos" e uma barra de ações que aparece no rodapé enquanto há itens marcados. Com a página inteira marcada, um aviso oferece "Selecionar todos os N" para agir sobre o filtro inteiro (todas as páginas).

| Tela | Ações em massa |
| --- | --- |
| Produtos | Adicionar a uma campanha, alterar categoria, tags, excluir |
| Fila | Aprovar ou liberar para reenviar, remover da fila e, nas abas Falhas e Canceladas, excluir de vez. Enviadas não são excluídas: contam para o prazo de repostagem |
| Achados | Aprovar e descartar (Para aprovar), descartar (Fora dos filtros), restaurar (Descartados) |
| Buscas | Ativar, pausar, excluir |
| Campanhas | Pausar, retomar, cancelar e excluir (cada uma só onde a campanha permite) |
| Grupos | Salvar como conjunto, ativar, desativar, remover do cadastro |
| Meu perfil | Excluir nichos |
| Busca da campanha | Excluir buscas do histórico (os produtos já adicionados ficam) |
| Configurações | Limpar o histórico do worker |

Toda exclusão pede confirmação dizendo o que acontece.

## Modelo da mensagem

Em **Meu perfil > Mensagem e foto** (ou na campanha, se ela personalizar), edite o texto da oferta com variáveis e veja a prévia ao vivo, já com o #publi no topo. Há modelos prontos: Padrão (nome em negrito, "De" riscado, preço em destaque e o aviso "Preço e estoque podem mudar a qualquer momento"), Direto ao ponto, Desconto em destaque e Com a loja. Variáveis de linha (a linha some se faltar o dado): `{titulo}`, `{preco_de}`, `{preco_por}`, `{link}`, `{loja}`, `{categoria}`. Variáveis opcionais (somem sem apagar a linha): `{condicao}` (" no Pix"), `{desconto}` (" (44% OFF)"), `{desconto_pct}` ("44"). **Restaurar modelo padrão** volta ao texto original.

## Testes

```sh
docker compose exec api pytest -q          # backend (74 testes)
pip install playwright pytest && playwright install chromium
pytest tests_e2e                            # extensão: leitura de preço, busca, link de afiliado e envio, com páginas simuladas
```

## API

REST em `/api`: `products` (inclui `/from-browser` e `/{id}/browser-data`), `publications` (inclui `/queue`, `/summary`, `/bulk/approve`, `/{id}/claim`, `/{id}/sent`, `/{id}/failed`), `automations/settings`, `searches` (inclui `/due`, `/{id}/run`, `/{id}/results`), `listings` (inclui `/approve`, `/accept-all`, `/discard`), `group-schedules`, `ml-categories` (inclui `/children`, `/search`, `/favorites`, `/sync`, `/import`), `niches`, `campaigns` (inclui `/options`, `/preview`, `/{id}/confirm`, `/pause`, `/resume`, `/cancel`, `/duplicate`, `/{id}/searches/{sid}/best`, `/{id}/searches/remove`), `publications/bulk/delete`, `listings/restore`, `DELETE automations/logs`, `automations/template-preview`, `automations/logs`, `auth/login`, `auth/password`. Listas aceitam `limit` e `offset` e devolvem o total no cabeçalho `X-Total-Count`.

Após 5 senhas erradas em 15 minutos para o mesmo e-mail e IP, o login fica bloqueado temporariamente. Tokens de usuários desativados deixam de valer na hora.
