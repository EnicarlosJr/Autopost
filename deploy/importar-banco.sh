#!/bin/sh
# Substitui o banco do SERVIDOR pelo banco exportado do seu computador (arquivo .dump do pg_dump -Fc).
# Uso, no servidor, dentro da pasta do projeto:  sh deploy/importar-banco.sh autopost.dump
# Antes de apagar qualquer coisa, salva uma cópia do banco atual do servidor em ./backups.
set -eu
cd "$(dirname "$0")/.."
FILE="${1:-}"
if [ -z "$FILE" ] || [ ! -f "$FILE" ]; then
  echo "Uso: sh deploy/importar-banco.sh autopost.dump   (o arquivo exportado do seu computador)" >&2
  exit 1
fi
compose="docker compose -f docker-compose.yml -f docker-compose.prod.yml --env-file .env.production"

echo "ATENÇÃO: os dados atuais do servidor serão substituídos pelos do arquivo $FILE."
printf "Digite SUBSTITUIR para continuar: "
read answer
[ "$answer" = "SUBSTITUIR" ] || { echo "Nada foi alterado."; exit 1; }

mkdir -p backups
copy="backups/antes-da-importacao-$(date +%Y%m%d-%H%M).sql.gz"
$compose up -d db
$compose exec -T db pg_dump -U autopost autopost | gzip > "$copy"
echo "Cópia do banco atual do servidor salva em $copy"

# Para quem escreve no banco, troca os dados e sobe tudo de novo (as migrações rodam ao subir a API).
$compose stop api worker scheduler
$compose exec -T db psql -v ON_ERROR_STOP=1 -U autopost autopost -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
$compose exec -T db pg_restore -U autopost -d autopost --no-owner --no-privileges < "$FILE"
$compose up -d
echo "Importação concluída. O login do painel passa a ser o do seu computador."
