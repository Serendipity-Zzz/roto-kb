#!/usr/bin/env bash
# Remote bootstrap for ROTO-KB with embedded Qdrant.
# Safe around the legacy kb-server namespace.
set -euo pipefail

APP_ROOT="${ROTO_KB_APP_ROOT:-/opt/roto-kb}"
DATA_ROOT="${ROTO_KB_DATA_ROOT:-/var/lib/roto-kb}"
ETC_ROOT="${ROTO_KB_ETC_ROOT:-/etc/roto-kb}"
LOG_ROOT="${ROTO_KB_LOG_ROOT:-/var/log/roto-kb}"
SERVICE_USER="${ROTO_KB_SERVICE_USER:-$(id -un)}"
SERVICE_GROUP="${ROTO_KB_SERVICE_GROUP:-$(id -gn)}"
PUBLIC_HOST="${ROTO_KB_PUBLIC_HOST:-kb.example.invalid}"
TLS_SAN="${ROTO_KB_TLS_SAN:-DNS:${PUBLIC_HOST}}"
STAMP=$(date -u +%Y%m%d-%H%M%S)

echo "[1/10] create isolated directories"
sudo mkdir -p "$APP_ROOT" "$DATA_ROOT/sources" "$DATA_ROOT/index/qdrant" "$ETC_ROOT/tls" "$LOG_ROOT"
sudo chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_ROOT" "$DATA_ROOT" "$LOG_ROOT"
sudo chown -R root:root "$ETC_ROOT"
sudo chmod 755 "$ETC_ROOT" "$ETC_ROOT/tls"

echo "[2/10] refuse legacy path collisions"
for p in /data/knowledge-base /var/lib/legacy-kb-server /opt/legacy-kb-server; do
  case "$DATA_ROOT" in
    "$p"|"$p"/*) echo "refusing to use legacy path $p"; exit 1 ;;
  esac
done

echo "[3/10] stop only the ROTO-KB unit and recover unowned embedded locks"
if sudo systemctl is-active --quiet roto-kb.service; then
  sudo systemctl stop roto-kb.service
fi
if ss -ltnp | grep -Eq '(^|[[:space:]])(0\.0\.0\.0|::):8710([[:space:]]|$)'; then
  echo "refusing deployment: ROTO-KB is not loopback-only on port 8710"
  exit 1
fi
if pgrep -af '[r]oto_kb|[u]vicorn.*8710|[q]drant' >/dev/null; then
  echo "refusing deployment: a ROTO-KB/Qdrant process still owns the data or port"
  pgrep -af '[r]oto_kb|[u]vicorn.*8710|[q]drant' || true
  exit 1
fi
while IFS= read -r lock_file; do
  [ -n "$lock_file" ] || continue
  sudo mv -- "$lock_file" "${lock_file}.stale-${STAMP}"
done < <(find "$DATA_ROOT/index/qdrant" -type f -name .lock -print)

echo "[4/10] python venv + install"
cd "$APP_ROOT"
python3.11 -m venv .venv
. .venv/bin/activate
pip install -U pip wheel
pip install -e .

echo "[5/10] sync knowledge sources (no legacy copy)"
rsync -a --delete \
  --exclude 'ontologies/iof-core/etc' \
  --exclude 'ontologies/iof-core/**/images' \
  --exclude 'ontologies/qudt/src/build' \
  "$APP_ROOT/knowledge/" "$DATA_ROOT/sources/"

echo "[6/10] install env/systemd/nginx artifacts"
if [[ ! -f "$ETC_ROOT/roto-kb.env" ]]; then
  echo "missing $ETC_ROOT/roto-kb.env"; exit 1
fi
sudo chmod 600 "$ETC_ROOT/roto-kb.env"
if [[ -f /etc/systemd/system/roto-kb.service ]]; then
  sudo cp /etc/systemd/system/roto-kb.service "$ETC_ROOT/roto-kb.service.bak-$STAMP"
fi
if [[ -f /etc/nginx/conf.d/roto-kb.conf ]]; then
  sudo cp /etc/nginx/conf.d/roto-kb.conf "$ETC_ROOT/nginx-roto-kb.conf.bak-$STAMP"
fi
sed \
  -e "s|@ROTO_KB_SERVICE_USER@|$SERVICE_USER|g" \
  -e "s|@ROTO_KB_SERVICE_GROUP@|$SERVICE_GROUP|g" \
  -e "s|@ROTO_KB_APP_ROOT@|$APP_ROOT|g" \
  -e "s|@ROTO_KB_DATA_ROOT@|$DATA_ROOT|g" \
  "$APP_ROOT/infra/roto-kb.service" | sudo tee /etc/systemd/system/roto-kb.service >/dev/null
sed "s|kb.example.invalid|$PUBLIC_HOST|g" \
  "$APP_ROOT/infra/nginx-roto-kb.conf" | sudo tee /etc/nginx/conf.d/roto-kb.conf >/dev/null

if [[ ! -f "$ETC_ROOT/tls/fullchain.pem" ]]; then
  echo "[7/10] create temporary self-signed cert"
  sudo openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
    -keyout "$ETC_ROOT/tls/privkey.pem" \
    -out "$ETC_ROOT/tls/fullchain.pem" \
    -subj "/CN=$PUBLIC_HOST" \
    -addext "subjectAltName=$TLS_SAN"
  sudo chmod 644 "$ETC_ROOT/tls/fullchain.pem"
  sudo chmod 600 "$ETC_ROOT/tls/privkey.pem"
else
  echo "[7/10] reuse existing TLS materials"
fi

echo "[8/10] validate network boundary and reload nginx"
if ss -ltnp | grep -Eq '(^|[[:space:]])(0\.0\.0\.0|::):(8710|6334)([[:space:]]|$)'; then
  echo "refusing deployment: app/Qdrant port is publicly bound"
  exit 1
fi
sudo systemctl daemon-reload
sudo systemctl enable roto-kb.service
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl restart roto-kb.service
sudo systemctl is-active roto-kb.service

echo "[9/10] smoke checks (loopback + public path)"
ready=0
for attempt in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8710/health; then
    ready=1
    break
  fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "ROTO-KB did not become ready within 30 seconds"
  sudo systemctl status roto-kb.service --no-pager || true
  exit 1
fi
if [[ -n "${ROTO_KB_PUBLIC_HOST:-}" ]]; then
  curl -sk --fail --resolve "$PUBLIC_HOST:443:127.0.0.1" "https://$PUBLIC_HOST/roto-kb/health"
  echo
else
  echo "public TLS smoke skipped; set ROTO_KB_PUBLIC_HOST for a real deployment"
fi
echo "[10/10] legacy namespace health (read-only isolation evidence)"
curl -sS --max-time 5 http://127.0.0.1:8700/health || true
echo
echo "deploy complete: legacy kb-server health printed above for isolation evidence"
