#!/bin/bash
# Abre a interface web do gerador de vídeos (duplo clique para iniciar)

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# garante acesso ao ffmpeg (Homebrew) e usa o Python do ambiente virtual
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
PYTHON="$DIR/.venv/bin/python3"

PORTA=8000
LOG=/tmp/gerador_web.log

# mata qualquer servidor antigo na porta (evita "porta em uso" e código desatualizado)
pkill -f "server.py $PORTA" 2>/dev/null
sleep 1

echo "Iniciando o gerador de vídeos..."
"$PYTHON" server.py "$PORTA" > "$LOG" 2>&1 &
PID=$!

# Espera o servidor subir (até 10 segundos)
ok=0
for i in $(seq 1 20); do
  sleep 0.5
  if curl -s -o /dev/null "http://127.0.0.1:$PORTA/"; then
    ok=1
    break
  fi
done

if [ "$ok" = "1" ]; then
  echo "Servidor no ar!"
  open "http://localhost:$PORTA"
  echo ""
  echo "=============================================="
  echo "  Interface: http://localhost:$PORTA"
  echo "  Mantenha esta janela aberta."
  echo "  Para parar, feche esta janela."
  echo "=============================================="
else
  echo ""
  echo "ERRO: o servidor não subiu. Últimas linhas do log:"
  tail -20 "$LOG"
  echo ""
fi

# Mantém a janela aberta
wait $PID 2>/dev/null
echo ""
echo "Servidor encerrado. Pressione Enter para fechar..."
read
