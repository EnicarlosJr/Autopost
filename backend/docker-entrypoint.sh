#!/bin/sh
# Ajusta o dono da pasta de imagens (volumes antigos foram criados como root)
# e roda o processo como o usuário "app", sem privilégios de root.
set -e
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/storage/products
    chown -R app:app /app/storage
    exec python -c 'import os, pwd, sys
user = pwd.getpwnam("app")
os.setgroups([])
os.setgid(user.pw_gid)
os.setuid(user.pw_uid)
os.environ["HOME"] = user.pw_dir
os.execvp(sys.argv[1], sys.argv[1:])' "$@"
fi
exec "$@"
