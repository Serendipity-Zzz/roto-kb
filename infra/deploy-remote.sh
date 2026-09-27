#!/usr/bin/env bash
# Remote bootstrap for ROTO-KB with embedded Qdrant.
# Safe around the legacy kb-server namespace.
set -euo pipefail

APP_ROOT=/home/ec2-user/roto-kb
DATA_ROOT=/data/roto-kb
ETC_ROOT=/etc/roto-kb
LOG_ROOT=/var/log/roto-kb
STAMP=$(date -u +%Y%m%d-%H%M%S)

echo "[1/10] create isolated directories"
sudo mkdir -p "$APP_ROOT" "$DATA_ROOT/sources" "$DATA_ROOT/index/qdrant" "$ETC_ROOT/tls" "$LOG_ROOT"
sudo chown -R ec2-user:ec2-user "$APP_ROOT" "$DATA_ROOT" "$LOG_ROOT"
sudo chown -R root:root "$ETC_ROOT"
sudo chmod 755 "$ETC_ROOT" "$ETC_ROOT/tls"

echo "[2/10] refuse legacy path collisions"
for p in /data/knowledge-base /home/ec2-user/.kb-server /home/ec2-user/kb-server; do
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
sudo cp "$APP_ROOT/infra/roto-kb.service" /etc/systemd/system/roto-kb.service
sudo cp "$APP_ROOT/infra/nginx-roto-kb.conf" /etc/nginx/conf.d/roto-kb.conf

if [[ ! -f "$ETC_ROOT/tls/fullchain.pem" ]]; then
  echo "[7/10] create temporary IP-SAN self-signed cert"
  sudo openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
    -keyout "$ETC_ROOT/tls/privkey.pem" \
    -out "$ETC_ROOT/tls/fullchain.pem" \
    -subj "/CN=54.172.101.190" \
    -addext "subjectAltName=IP:54.172.101.190"
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
curl -sk --fail --resolve 54.172.101.190:443:127.0.0.1 https://54.172.101.190/roto-kb/health
echo
echo "[10/10] legacy namespace health (read-only isolation evidence)"
curl -sS --max-time 5 http://127.0.0.1:8700/health || true
echo
echo "deploy complete: legacy kb-server health printed above for isolation evidence"
