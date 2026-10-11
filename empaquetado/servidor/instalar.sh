#!/bin/sh
# Instala y arranca mufa en un servidor Linux con Docker.
set -eu
cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "Falta Docker. Instálalo con: curl -fsSL https://get.docker.com | sh" >&2
  exit 1
fi
[ -f .env ] || cp .env.ejemplo .env

docker compose up -d
echo "Esperando a que mufa arranque..."
for _ in $(seq 1 30); do
  if docker compose logs mufa 2>/dev/null | grep -q "token"; then break; fi
  sleep 2
done
docker compose logs mufa | grep -A1 "token" || true
dominio=$(grep -E '^MUFA_DOMINIO=' .env | cut -d= -f2)
echo
echo "Abre https://${dominio:-localhost}/ y crea el administrador con el token de arriba."
