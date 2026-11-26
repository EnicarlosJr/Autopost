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

## Como fica o conjunto

- **Servidor (VPS):** painel, API, campanhas, agenda e páginas dos pais. Fica ligado 24 h.
- **Computador robô (em casa):** um mini PC ou notebook sempre ligado, só com o Chrome, a extensão, a conta de afiliado do ML e o WhatsApp Web. Ele lê o Mercado Livre e envia as mensagens (veja a seção 8). A internet é a de casa, então o ML e o WhatsApp tratam igual a hoje.
- **Você:** usa o painel online de qualquer lugar (celular ou computador). O seu computador não precisa ficar ligado.

## 1. Servidor e domínio

- **VPS** com Ubuntu 24.04 LTS, 2 GB de RAM (4 GB se usar muito as buscas) e 20 GB de disco. De preferência com datacenter em São Paulo, que deixa o painel mais rápido e mantém os dados no Brasil (ex.: Vultr, AWS Lightsail, Magalu Cloud). Hetzner, DigitalOcean e Contabo também servem, fora do Brasil. Ative os **backups automáticos do provedor** se houver (custam pouco).
- **Domínio** `.com.br` no Registro.br (cerca de R$ 40 por ano).
- No DNS do domínio, crie dois registros **A** apontando para o IP do servidor: `painel` e `listas` (ou os nomes que preferir). Se usar a Cloudflare, deixe esses dois como "DNS only" (nuvem cinza): o HTTPS é feito pelo Caddy.
- Ao criar a VPS, cadastre a sua **chave SSH** (o provedor mostra como) em vez de senha.

## 2. Preparar o servidor (uma vez)

Entre no servidor por SSH (`ssh root@IP-DO-SERVIDOR`). Atualize o sistema e ligue as atualizações de segurança automáticas:

```bash
apt update && apt -y upgrade && apt -y install unattended-upgrades git
```

```bash
dpkg-reconfigure -plow unattended-upgrades
```

Instale o Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

Libere só SSH, HTTP e HTTPS no firewall:

```bash
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw enable
```

Baixe o projeto (branch `main`). Repositório público:

```bash
git clone -b main https://github.com/EnicarlosJr/Autopost.git autopost
```

Repositório privado: crie uma chave só de leitura no servidor (`ssh-keygen -t ed25519 -f ~/.ssh/autopost -N ""`), cadastre o conteúdo de `~/.ssh/autopost.pub` no GitHub em **Settings > Deploy keys** do repositório (sem marcar "Allow write access") e clone por SSH:

```bash
GIT_SSH_COMMAND="ssh -i ~/.ssh/autopost" git clone -b main git@github.com:EnicarlosJr/Autopost.git autopost
```

```bash
cd autopost && git config core.sshCommand "ssh -i ~/.ssh/autopost"
```

```bash
cd autopost && cp .env.production.example .env.production
```

Edite o `.env.production` (`nano .env.production`): os dois domínios, o e-mail do certificado e **todos** os segredos. Para gerar cada segredo:

```bash
openssl rand -base64 48
```

## 3. Subir

**Atalho para a primeira vez:** `sh deploy/primeira-instalacao.sh seudominio.com.br seu-email@exemplo.com` cria o `.env.production` com senhas geradas no próprio servidor, espera o DNS apontar para o servidor, sobe tudo e mostra o login do painel. Nas próximas vezes, use só o `deploy.sh`.

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

## 8. Computador robô (Chrome sempre ligado em casa)

Qualquer mini PC ou notebook com Windows 10/11 ou Linux, 4 GB de RAM, ligado na internet de casa (de preferência por cabo).

1. **Energia:** nas configurações de energia, "Nunca" para suspender e para desligar a tela. No BIOS, se houver, ligue "ligar quando a energia voltar" (Restore on AC Power Loss).
2. **Chrome:** instale o Chrome e crie um perfil só para o Autopost.
3. **Extensão:** baixe a pasta `extension` da branch `main` (pelo `git clone` ou "Code > Download ZIP" no GitHub). Em `chrome://extensions`, ligue o "Modo do desenvolvedor" e use "Carregar sem compactação" apontando para a pasta `extension`.
4. **Opções da extensão:** em "Painel online (produção)", coloque `https://painel.seudominio.com.br`, salve e aceite a permissão. Abra o painel online nesse Chrome e faça login.
5. **Contas:** entre na sua conta de afiliado do Mercado Livre e abra o WhatsApp Web (leia o QR code com o celular). Deixe as duas abas abertas.
6. **Chrome tratando a janela como visível:** abra o Chrome por um atalho com `--disable-backgrounding-occluded-windows` (no Windows: atalho com `"C:\Program Files\Google\Chrome\Application\chrome.exe" --disable-backgrounding-occluded-windows`). Coloque esse atalho na pasta de inicialização (`Win+R`, `shell:startup`) para abrir sozinho quando o computador ligar.
7. **Acesso remoto para manutenção:** instale o Chrome Remote Desktop (remotedesktop.google.com) com um PIN forte. Assim você confere o robô pelo celular sem ir até ele.
8. **Bloqueio de tela:** não bloqueie a tela (o envio pelo WhatsApp Web precisa da janela ativa). Por isso, deixe o robô num lugar da casa sem acesso de estranhos e use o robô só para o Autopost.

Quando a extensão mudar (versão nova na `main`), atualize a pasta `extension` no robô, clique em Recarregar em `chrome://extensions` e aperte F5 no painel.

## Cuidados

- O repositório no GitHub está **público**: qualquer pessoa vê o código. Nenhum segredo vai para o git, mas considere torná-lo privado (Settings > General > Danger Zone > Change visibility) e use a chave de leitura da seção 2.
- `.env.production` e `backups/` ficam fora do git. Nunca envie esses arquivos para o GitHub nem cole os valores em conversas.
- A página das listas guarda nome de aluno e turma (dados de menor, LGPD): mantenha os backups em lugar protegido.
- Nunca rode `docker compose down -v` no servidor: o `-v` apaga o banco.
- O envio pelo WhatsApp continua saindo do seu Chrome. Colocar o sistema online não muda os cuidados do roteiro de regularização.
