#!/bin/bash
# Reinicio seguro: valida que el código importe ANTES de reiniciar (si falla, el sitio sigue con la versión anterior).
set -e
cd /home/hackaton/creador-ia
chown -R hackaton:hackaton .
if ! sudo -u hackaton .venv/bin/python -c "import app.main" 2>/tmp/marcia-import.err; then
  echo "❌ El código no importa: NO se reinicia."; cat /tmp/marcia-import.err | tail -5; exit 1
fi
systemctl restart marcia
for i in 1 2 3 4 5 6 7 8 9 10; do sleep 1; curl -sf -o /dev/null http://127.0.0.1:8000/salud && { echo "✅ marcia reiniciado y respondiendo"; exit 0; }; done
echo "❌ marcia no responde tras reiniciar"; journalctl -u marcia -n 20 --no-pager; exit 1
