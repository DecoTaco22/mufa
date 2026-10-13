#!/bin/sh
# Instala (o actualiza) mufa en un servidor Linux con Docker.
#
#   sh instalar.sh                  pregunta con qué dirección van a entrar
#   sh instalar.sh 192.168.1.50     sin preguntar: la IP o el dominio
#   sh instalar.sh mufa.miisp.com
#
# Se puede ejecutar las veces que haga falta: conserva .env y los datos.
set -eu
cd "$(dirname "$0")"

falla() {
  printf '\n  ✗ %s\n\n' "$1" >&2
  exit 1
}

# 1. Lo que hace falta ------------------------------------------------------
case "$(uname -m)" in
  x86_64 | amd64) ;;
  *) falla "mufa todavía funciona solo en servidores de 64 bits Intel o AMD (x86_64); este es $(uname -m)." ;;
esac
command -v docker >/dev/null 2>&1 ||
  falla "Falta Docker. Instálalo con:  curl -fsSL https://get.docker.com | sudo sh
    y vuelve a ejecutar:  sh instalar.sh"
docker compose version >/dev/null 2>&1 ||
  falla "Falta «docker compose». En Debian o Ubuntu:  sudo apt install docker-compose-plugin"
if ! docker info >/dev/null 2>&1; then
  if [ "$(id -u)" != 0 ]; then
    falla "Tu usuario no puede usar Docker. Ejecuta:  sudo sh instalar.sh"
  fi
  falla "Docker no responde. Enciéndelo con:  systemctl start docker"
fi

# 2. Con qué dirección se va a entrar --------------------------------------
[ -f .env ] || cp .env.ejemplo .env
actual=$(sed -n 's/^MUFA_DOMINIO=//p' .env)
ip=$(hostname -I 2>/dev/null | awk '{print $1}')
[ -n "$ip" ] || ip=$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p')

if [ $# -ge 1 ]; then
  direccion=$1
elif [ -n "$actual" ] && [ "$actual" != localhost ]; then
  direccion=$actual # ya se eligió en una instalación anterior
elif [ -t 0 ]; then
  echo
  echo "  ¿Con qué dirección van a entrar a mufa desde el navegador?"
  echo "   • Un dominio que apunte a este servidor (ej. mufa.miisp.com): el certificado"
  echo "     HTTPS sale solo y es válido. Necesita los puertos 80 y 443 abiertos."
  echo "   • La IP de este servidor${ip:+ ($ip)}: funciona dentro de tu red; el navegador"
  echo "     avisa del certificado la primera vez."
  printf '\n  Dirección [%s]: ' "${ip:-localhost}"
  read -r direccion
  [ -n "$direccion" ] || direccion=${ip:-localhost}
else
  direccion=${ip:-localhost}
fi
# Sin https://, sin barra ni puerto: solo el nombre o la IP.
direccion=$(printf '%s' "$direccion" | sed 's|^[a-zA-Z]*://||; s|/.*$||; s|:[0-9]*$||')
printf '%s' "$direccion" | grep -Eq '^[A-Za-z0-9.-]+$' ||
  falla "«$direccion» no es una IP ni un dominio válido."
sed -i "s|^MUFA_DOMINIO=.*|MUFA_DOMINIO=$direccion|" .env

# La zona horaria del servidor, si el .env sigue con la de ejemplo.
zona=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || true)
if [ -n "$zona" ] && [ "$zona" != UTC ] && [ "$zona" != Etc/UTC ] &&
  grep -q '^TZ=America/Guatemala$' .env; then
  sed -i "s|^TZ=.*|TZ=$zona|" .env
fi

# 3. Arrancar ---------------------------------------------------------------
echo
echo "  Descargando y arrancando mufa (la primera vez tarda un par de minutos)..."
if ! docker compose up -d --remove-orphans; then
  falla "No se pudo arrancar. Si dice «port is already allocated» o «address already
    in use», otro programa (Apache, Nginx...) usa el puerto 80 o 443: detenlo y
    vuelve a ejecutar  sh instalar.sh"
fi

listo=""
for _ in $(seq 1 60); do
  if docker compose exec -T mufa python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/v1/salud')" \
    >/dev/null 2>&1; then
    listo=1
    break
  fi
  sleep 2
done
[ -n "$listo" ] || falla "mufa no arrancó. Para ver qué pasó:  docker compose logs mufa"
token=$(docker compose exec -T mufa cat /datos/token-primera-vez.txt 2>/dev/null | tr -d '\r\n' || true)

# 4. Qué hacer ahora ---------------------------------------------------------
echo
echo "  ✓ mufa está funcionando."
echo
echo "    Abre:   https://$direccion/"
if [ -n "$token" ]; then
  echo "    Token:  $token"
  echo "            (lo pide una sola vez, para crear la cuenta de administrador)"
else
  echo "            Entra con tu usuario de siempre."
fi
echo
if printf '%s' "$direccion" | grep -Eq '^[0-9.]+$|^localhost$'; then
  echo "    El navegador va a avisar que la conexión no es privada: es el certificado"
  echo "    propio de mufa. Elige «Configuración avanzada» > «Continuar»."
else
  echo "    Si el navegador no abre, revisa que $direccion apunte a este servidor"
  echo "    y que los puertos 80 y 443 estén abiertos."
fi
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  echo
  echo "    El firewall (ufw) está activo. Si no abre, permite HTTPS:  sudo ufw allow 80,443/tcp"
fi
echo
echo "    Ver qué pasa:  docker compose logs -f mufa      Detener:  docker compose down"
echo
