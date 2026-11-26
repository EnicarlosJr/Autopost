#!/bin/sh
# Primeira instalação no servidor (Ubuntu 24.04), dentro da pasta do projeto:
#   sh deploy/primeira-instalacao.sh base92.com.br voce@exemplo.com
# 1) cria o .env.production com senhas geradas aqui mesmo (nada passa por conversa ou e-mail);
# 2) espera o DNS de painel.<domínio> e listas.<domínio> apontar para este servidor;
# 3) sobe tudo com deploy/deploy.sh e mostra os dados do primeiro login.
set -eu
cd "$(dirname "$0")/.."
DOMINIO="${1:-}"
EMAIL="${2:-}"
if [ -z "$DOMINIO" ] || [ -z "$EMAIL" ]; then
  echo "Uso: sh deploy/primeira-instalacao.sh seudominio.com.br seu-email@exemplo.com" >&2
  exit 1
fi

if grep -q "^PANEL_DOMAIN=painel.$DOMINIO$" .env.production 2>/dev/null; then
  echo "O .env.production já existe para $DOMINIO: mantendo as senhas atuais."
else
  if [ -f .env.production ]; then
    mv .env.production ".env.production.antigo-$(date +%Y%m%d%H%M%S)"
    echo "O .env.production anterior (de outro domínio) foi guardado com o sufixo .antigo-..."
  fi
  umask 077
  cat > .env.production <<EOF
PANEL_DOMAIN=painel.$DOMINIO
PUBLIC_DOMAIN=listas.$DOMINIO
ACME_EMAIL=$EMAIL
JWT_SECRET=$(openssl rand -hex 32)
ADMIN_EMAIL=$EMAIL
ADMIN_PASSWORD=$(openssl rand -base64 24 | tr -d '/+=')
POSTGRES_PASSWORD=$(openssl rand -hex 24)
REPOST_WINDOW_HOURS=24
PRICE_MAX_AGE_HOURS=6
LOG_RETENTION_DAYS=30
EOF
  chmod 600 .env.production
  echo "Criei o .env.production com senhas novas."
fi

IP="$(curl -fsS https://api.ipify.org || hostname -I | awk '{print $1}')"
echo "IP deste servidor: $IP"
echo "No Registro.br, os registros A 'painel' e 'listas' de $DOMINIO precisam apontar para $IP."
resolve() { getent ahostsv4 "$1" | awk 'NR==1{print $1}'; }
while [ "$(resolve "painel.$DOMINIO")" != "$IP" ] || [ "$(resolve "listas.$DOMINIO")" != "$IP" ]; do
  echo "Aguardando o DNS (painel: $(resolve "painel.$DOMINIO" || true); listas: $(resolve "listas.$DOMINIO" || true)). Nova tentativa em 1 min. Ctrl+C para sair."
  sleep 60
done
echo "DNS ok."

sh deploy/deploy.sh

echo
echo "Pronto. Painel: https://painel.$DOMINIO"
echo "Login do painel (guarde a senha num gerenciador de senhas e não compartilhe):"
grep -E "^ADMIN_(EMAIL|PASSWORD)=" .env.production
