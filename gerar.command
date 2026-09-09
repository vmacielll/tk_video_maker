#!/bin/bash
# Gera vídeos a partir das pastas em "entrada/" (duplo clique para executar)

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

"$DIR/.venv/bin/python3" gerar.py
echo ""
echo "--------------------------------------"
echo "Pronto! Os vídeos estão na pasta 'saida'."
echo "Pressione Enter para fechar esta janela..."
read
