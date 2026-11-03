#!/bin/bash
# Instaleaza mpv-agent pe un Raspberry Pi / Debian. Te intreaba fiecare valoare, pe rand, in consola
# (Enter = valoarea din paranteza), scrie singur .env, apoi face tot restul: pachete, utilizator de serviciu,
# cheia tunelului (generata daca lipseste), known_hosts (cu confirmare de amprenta), serviciul systemd.
# Poate fi rulat din nou: valorile din .env existent devin valorile implicite.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$HERE/.env"
APP=/opt/mpv-agent
SVC=mpv-agent

if [ "$(id -u)" -ne 0 ] && [ -z "${MPV_INSTALL_DRY:-}" ]; then exec sudo "$0" "$@"; fi

old() { [ -f "$ENV_FILE" ] && grep -E "^$1=" "$ENV_FILE" | head -1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' || true; }

# ask VAR "intrebare" "implicit" [optional]
ask() {
  local var="$1" q="$2" def="$3" opt="${4:-}" prev ans
  prev="$(old "$var")"; [ -n "$prev" ] && def="$prev"
  while true; do
    if [ -n "$def" ]; then read -r -p "$q [$def]: " ans; ans="${ans:-$def}"
    elif [ -n "$opt" ]; then read -r -p "$q (optional, Enter = gol): " ans
    else read -r -p "$q: " ans; fi
    if [ -n "$ans" ] || [ -n "$opt" ]; then break; fi
    echo "  Valoarea e obligatorie."
  done
  printf -v "$var" '%s' "$ans"
}

echo "=== Configurare mpv-agent (Enter = valoarea din paranteza) ==="
echo
ask SSH_TARGET      "Serverul catre care se face tunelul, ca utilizator@adresa" ""
ask REMOTE_PROGRAM  "Calea lui program.json pe server" ""
ask REMOTE_CLIPS_DIR "Calea folderului cu fisiere (clipuri/poze) pe server" ""
ask VPS_BIND        "Adresa pe care asculta tunelul pe server (ex. 127.0.0.1 sau 172.17.0.1)" "127.0.0.1"
ask VPS_PORT        "Portul tunelului pe server" "18080"
ask AGENT_PORT      "Portul HTTP local al agentului (doar 127.0.0.1)" "8765"
ask MPV_ARGS        "Argumente mpv (rezolutia HDMI)" "--drm-mode=1280x720"
ask DRM_CONNECTOR   "Conector DRM, ex. HDMI-A-1" "" optional
ask SERVICE_USER    "Utilizatorul sub care ruleaza serviciul (se creeaza daca nu exista)" "mpv-agent"
ask CACHE_DIR       "Folderul unde tine agentul programul si fisierele descarcate" "/var/lib/$SERVICE_USER"
ask SSH_KEY         "Calea cheii SSH a tunelului (se genereaza daca nu exista)" "$CACHE_DIR/.ssh/tunnel_ed25519"
ask SSH_KNOWN_HOSTS "Calea fisierului known_hosts" "$CACHE_DIR/.ssh/known_hosts"
ask MPV_SOCKET      "Calea socketului mpv" "/run/$SERVICE_USER/mpv.sock"

for p in "$VPS_PORT" "$AGENT_PORT"; do
  case "$p" in ''|*[!0-9]*) echo "Port invalid: $p"; exit 1;; esac
  [ "$p" -ge 1 ] && [ "$p" -le 65535 ] || { echo "Port invalid: $p"; exit 1; }
done

umask 077
{
  echo "SSH_TARGET=$SSH_TARGET"
  echo "SSH_KEY=$SSH_KEY"
  echo "SSH_KNOWN_HOSTS=$SSH_KNOWN_HOSTS"
  echo "REMOTE_PROGRAM=$REMOTE_PROGRAM"
  echo "REMOTE_CLIPS_DIR=$REMOTE_CLIPS_DIR"
  echo "VPS_BIND=$VPS_BIND"
  echo "VPS_PORT=$VPS_PORT"
  echo "AGENT_PORT=$AGENT_PORT"
  echo "CACHE_DIR=$CACHE_DIR"
  echo "MPV_SOCKET=$MPV_SOCKET"
  echo "MPV_ARGS=$MPV_ARGS"
  echo "SERVICE_USER=$SERVICE_USER"
  [ -n "$DRM_CONNECTOR" ] && echo "DRM_CONNECTOR=$DRM_CONNECTOR"
} > "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
echo
echo "Am scris $ENV_FILE"
[ -n "${MPV_INSTALL_DRY:-}" ] && exit 0
read -r -p "Continui cu instalarea? [Y/n] " go
case "${go:-y}" in n|N) echo "Oprit. Rulezi din nou ./install.sh cand vrei (valorile raman ca implicite)."; exit 0;; esac

HOST="${SSH_TARGET#*@}"

echo "== pachete"
apt-get install -y --no-install-recommends mpv rsync python3 openssh-client >/dev/null

echo "== utilizator $SERVICE_USER"
id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --create-home --home-dir "$CACHE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
for g in video render; do getent group "$g" >/dev/null && usermod -aG "$g" "$SERVICE_USER"; done
mkdir -p "$CACHE_DIR" "$(dirname "$SSH_KEY")" "$(dirname "$SSH_KNOWN_HOSTS")"
chown "$SERVICE_USER:$SERVICE_USER" "$CACHE_DIR"; chmod 700 "$(dirname "$SSH_KEY")"

echo "== cheia tunelului"
if [ ! -f "$SSH_KEY" ]; then ssh-keygen -q -t ed25519 -N "" -C "mpv-agent@$(hostname)" -f "$SSH_KEY"; echo "generata: $SSH_KEY"; else echo "exista deja: $SSH_KEY"; fi

echo "== known_hosts (verificare stricta a serverului)"
if ! grep -q . "$SSH_KNOWN_HOSTS" 2>/dev/null; then
  ssh-keyscan -t ed25519 "$HOST" > "$SSH_KNOWN_HOSTS.tmp" 2>/dev/null
  [ -s "$SSH_KNOWN_HOSTS.tmp" ] || { rm -f "$SSH_KNOWN_HOSTS.tmp"; echo "Nu pot citi cheia serverului $HOST (e accesibil?)"; exit 1; }
  echo "Amprenta serverului $HOST:"; ssh-keygen -lf "$SSH_KNOWN_HOSTS.tmp"
  read -r -p "Este amprenta corecta? [y/N] " ans
  [ "$ans" = y ] || { rm -f "$SSH_KNOWN_HOSTS.tmp"; echo "Anulat."; exit 1; }
  mv "$SSH_KNOWN_HOSTS.tmp" "$SSH_KNOWN_HOSTS"
else echo "exista deja: $SSH_KNOWN_HOSTS"; fi
chown -R "$SERVICE_USER:$SERVICE_USER" "$(dirname "$SSH_KEY")" "$(dirname "$SSH_KNOWN_HOSTS")"; chmod 600 "$SSH_KEY"

echo "== fisiere in $APP"
mkdir -p "$APP"
install -m 755 "$HERE/agent.py" "$APP/agent.py"
install -m 600 -o "$SERVICE_USER" -g "$SERVICE_USER" "$ENV_FILE" "$APP/.env"

SOCK_DIR=$(basename "$(dirname "$MPV_SOCKET")"); STATE_DIR=$(basename "$CACHE_DIR")
cat > /etc/systemd/system/$SVC.service <<UNIT
[Unit]
Description=mpv-agent (tunel SSH, sync, redare mpv)
After=network.target

[Service]
User=$SERVICE_USER
Group=$SERVICE_USER
SupplementaryGroups=video render
RuntimeDirectory=$SOCK_DIR
StateDirectory=$STATE_DIR
ExecStart=/usr/bin/python3 -I $APP/agent.py
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target
UNIT

echo "== serviciu"
systemctl daemon-reload
systemctl enable $SVC >/dev/null 2>&1
systemctl restart $SVC
sleep 3
systemctl is-active $SVC

echo
echo "== DE FACUT PE SERVER (o singura data): adauga in ~/.ssh/authorized_keys al utilizatorului ${SSH_TARGET%@*} linia:"
echo
echo "restrict,port-forwarding,permitlisten=\"$VPS_BIND:$VPS_PORT\" $(cat "$SSH_KEY.pub")"
echo
echo "(Linia permite doar tunelul pe $VPS_BIND:$VPS_PORT. Pentru citire limitata la un folder, adauga in fata"
echo " command=\"rrsync -ro /folderul/cu/fisiere\" si foloseste cai relative la acel folder.)"
echo "Dupa ce ai adaugat linia, agentul isi face singur tunelul (jurnal: journalctl -u $SVC -f)."
