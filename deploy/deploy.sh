#!/bin/sh
# Atualiza o servidor com a branch main (produção) e sobe os containers.
# Uso, no servidor, dentro da pasta do projeto:  sh deploy/deploy.sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env.production ]; then
  echo "Falta o arquivo .env.production. Copie de .env.production.example e preencha." >&2
  exit 1
fi
git fetch origin main
git checkout main
git pull --ff-only origin main
compose="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production"
$compose up -d --build
$compose ps
echo "Pronto. As migrações do banco rodam sozinhas ao subir a API."
