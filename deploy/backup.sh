#!/bin/sh
# Roda dentro do container "backup" (produção): uma cópia do banco por dia em /backups (pasta ./backups no servidor).
# Mantém só os arquivos dos últimos 14 dias.
set -u
while true; do
  file="/backups/autopost-$(date +%Y%m%d-%H%M).sql.gz"
  if pg_dump -h db -U autopost autopost | gzip > "$file.tmp"; then
    mv "$file.tmp" "$file"
    echo "backup salvo: $file"
  else
    echo "backup falhou" >&2
  fi
  find /backups -maxdepth 1 -name 'autopost-*.sql.gz*' -mtime +14 -delete
  sleep 86400
done
