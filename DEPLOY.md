# Autopost online: deploy no servidor

Guia para colocar o Autopost num servidor (VPS) com domínio próprio e HTTPS. O uso no dia a dia continua igual: a extensão no seu Chrome lê o Mercado Livre e envia pelo WhatsApp Web; ela só passa a falar com o servidor em vez do seu computador.

## Branches

| Branch | Para quê | Onde roda |
| --- | --- | --- |
| `develop` | Atualizações e testes | Seu computador (`docker compose up --build -d`, painel em `localhost:5173`) |
| `main` | Produção: só o que já foi testado | Servidor (`sh deploy/deploy.sh`) |

Fluxo:
1. Trabalhe e teste na `develop` (no seu computador).
2. Quando estiver bom, junte a `develop` na `main` (pull request no GitHub, de `develop` para `main`).
3. No servidor, rode `sh deploy/deploy.sh`: ele baixa a `main` e reinicia os containers. As migrações do banco rodam sozinhas.

O mesmo código serve para os dois. O que muda é a configuração: `docker-compose.yml` + `.env` no local; `docker-compose.yml` + `docker-compose.prod.yml` + `.env.production` no servidor.

## O que fica na internet

Dois endereços (subdomínios do seu domínio), os dois com HTTPS automático (Caddy + Let's Encrypt):

| Endereço | Exemplo | O que abre |
| --- | --- | --- |
| `PANEL_DOMAIN` | `painel.seudominio.com.br` | Painel e API (com login). Só você usa. |
| `PUBLIC_DOMAIN` | `listas.seudominio.com.br` | Só as páginas dos pais (`/escolas/...`) e as fotos. Painel, API e documentação dão 404 aqui. |

Banco, Redis e API não têm porta aberta: só o Caddy escuta (80 e 443). A documentação da API (`/docs`) fica desligada. A API não sobe com segredo de exemplo ou fraco.

## 1. Servidor e domínio

- VPS com Ubuntu 24.04, 2 GB de RAM e 20 GB de disco (Hetzner, DigitalOcean, Contabo e similares).
- Um domínio (ex.: `.com.br` no Registro.br).
- No DNS do domínio, crie dois registros **A** apontando para o IP do servidor: `painel` e `listas` (ou os nomes que preferir). Se usar a Cloudflare, deixe esses dois como "DNS only" (nuvem cinza): o HTTPS é feito pelo Caddy.

## 2. Preparar o servidor (uma vez)

Entre no servidor por SSH e instale o Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

Libere só SSH, HTTP e HTTPS no firewall:

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
```

Baixe o projeto (branch `main`):

```bash
git clone -b main https://github.com/EnicarlosJr/Autopost.git autopost
```

```bash
cd autopost && cp .env.production.example .env.production
```

Edite o `.env.production` (`nano .env.production`): os dois domínios, o e-mail do certificado e **todos** os segredos. Para gerar cada segredo:

```bash
openssl rand -base64 48
```

## 3. Subir

```bash
sh deploy/deploy.sh
```

Na primeira vez o Caddy pede os certificados HTTPS (leva até 1 minuto). Confira:

- `https://painel.seudominio.com.br` abre o login do painel.
- `https://listas.seudominio.com.br/api/health` dá **404** (a API não fica aberta no endereço público).
- O link das listas no painel passa a ser `https://listas.seudominio.com.br/escolas/<escola>`.

## 4. Extensão do Chrome

1. Em `chrome://extensions`, recarregue a extensão (versão 2.15.0 ou maior).
2. Abra as **Opções** da extensão e preencha **Painel online (produção)** com `https://painel.seudominio.com.br`. Clique em Salvar e aceite a permissão que o Chrome pedir.
3. Abra o painel online e faça login. A extensão passa a usar a API do servidor.

Para voltar a testar no computador, apague o campo e salve: a extensão volta a usar o painel local (`localhost:5173`).

## 5. Levar os dados do computador para o servidor (opcional, antes do passo 3)

No seu computador (na `develop`, com o Docker rodando), exporte o banco:

```bash
docker compose exec -T db pg_dump -U autopost autopost > autopost.sql
```

Envie o arquivo para o servidor (ex.: `scp autopost.sql usuario@IP:~/autopost/`). Faça a importação **antes do passo 3** (antes da API subir pela primeira vez e criar um banco vazio). Suba só o banco:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production up -d db
```

Importe:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production exec -T db psql -U autopost autopost < autopost.sql
```

Depois siga o passo 3 (`sh deploy/deploy.sh`). O login continua o do seu computador.

As fotos dos produtos são baixadas de novo quando precisar.

## 6. Backups

O container `backup` salva uma cópia do banco por dia em `./backups` no servidor e mantém os últimos 14 dias. Copie essa pasta para fora do servidor de vez em quando (ex.: `scp -r usuario@IP:~/autopost/backups .`).

Restaurar um backup (substitui os dados atuais: faça só com certeza):

```bash
gunzip -c backups/autopost-AAAAMMDD-HHMM.sql.gz | docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production exec -T db psql -U autopost autopost
```

## 7. Atualizar a produção

1. Teste na `develop` no seu computador.
2. No GitHub, abra um pull request de `develop` para `main` e junte.
3. No servidor: `sh deploy/deploy.sh`.
4. Se a extensão mudou: recarregue em `chrome://extensions` e aperte F5 no painel.

## Cuidados

- `.env.production` e `backups/` ficam fora do git. Nunca envie esses arquivos para o GitHub nem cole os valores em conversas.
- A página das listas guarda nome de aluno e turma (dados de menor, LGPD): mantenha os backups em lugar protegido.
- Nunca rode `docker compose down -v` no servidor: o `-v` apaga o banco.
- O envio pelo WhatsApp continua saindo do seu Chrome. Colocar o sistema online não muda os cuidados do roteiro de regularização.
