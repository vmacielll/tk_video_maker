#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI: gera vídeos a partir de pastas em "entrada/".

Estrutura esperada:
    entrada/
        nome-do-video/
            fundo.jpg       (ou .png/.jpeg/.webp)
            textos.txt      (uma frase por linha)
    saida/                  (vídeos .mp4 gerados)
    config.txt              (opcional)

Config opcional (config.txt):
    duracao   = 2.5
    fade      = 0.4
    fonte     = georgia bold
    cor       = 255,255,255
    escurecer = 70
    template  = cartao   (opcional; se ausente/inválido, sorteia)
"""

import os
import sys

import nucleo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENTRADA = os.path.join(BASE_DIR, "entrada")
SAIDA = os.path.join(BASE_DIR, "saida")
EXTENSOES_IMG = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def carregar_config():
    cfg = {
        "duracao": nucleo.DURACAO_PADRAO,
        "fade": nucleo.FADE_PADRAO,
        "fonte": nucleo.FONTE_PADRAO,
        "cor": list(nucleo.COR_PADRAO),
        "escurecer": nucleo.ESCURECER_PADRAO,
        "template": None,
    }
    caminho = os.path.join(BASE_DIR, "config.txt")
    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                k, v = [x.strip() for x in linha.split("=", 1)]
                k = k.lower()
                if k == "duracao":
                    cfg["duracao"] = float(v)
                elif k == "fade":
                    cfg["fade"] = float(v)
                elif k == "fonte":
                    cfg["fonte"] = v.lower()
                elif k == "cor":
                    cfg["cor"] = [int(x) for x in v.split(",")]
                elif k == "escurecer":
                    cfg["escurecer"] = int(v)
                elif k == "template":
                    cfg["template"] = v.lower()
    return cfg


def achar_imagem(pasta):
    for nome in os.listdir(pasta):
        if nome.lower().startswith("fundo") and nome.lower().endswith(EXTENSOES_IMG):
            return os.path.join(pasta, nome)
    for nome in os.listdir(pasta):
        if nome.lower().endswith(EXTENSOES_IMG):
            return os.path.join(pasta, nome)
    return None


def ler_textos(caminho):
    frases = []
    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            frases.append(linha)
    return frases


def processar_pasta(nome, cfg):
    pasta = os.path.join(ENTRADA, nome)
    caminho_img = achar_imagem(pasta)
    if caminho_img is None:
        print("  [ERRO] nenhuma imagem de fundo em %s" % pasta)
        return None
    caminho_txt = os.path.join(pasta, "textos.txt")
    if not os.path.exists(caminho_txt):
        print("  [ERRO] falta o textos.txt em %s" % pasta)
        return None
    frases = ler_textos(caminho_txt)
    if not frases:
        print("  [ERRO] textos.txt vazio em %s" % pasta)
        return None

    # Se o template do config for ausente/inválido, sorteia automaticamente.
    template = cfg.get("template")
    if not template or template not in nucleo.TEMPLATES:
        template = nucleo.sortear_template()

    opcoes = {
        "duracao": cfg["duracao"],
        "fade": cfg["fade"],
        "fonte": cfg["fonte"],
        "cor": tuple(cfg["cor"]),
        "escurecer": cfg["escurecer"],
        "template": template,
        "cor_destaque": nucleo.COR_DESTAQUE_PADRAO,
        "nome": nome,
        "saida_dir": SAIDA,
    }
    return nucleo.gerar_video(caminho_img, frases, opcoes)


def main():
    os.makedirs(ENTRADA, exist_ok=True)
    os.makedirs(SAIDA, exist_ok=True)
    cfg = carregar_config()

    pastas = [p for p in os.listdir(ENTRADA)
              if os.path.isdir(os.path.join(ENTRADA, p)) and not p.startswith(".")]
    if not pastas:
        print("Nenhuma pasta encontrada em %s" % ENTRADA)
        print('Crie uma pasta com "fundo.jpg" e "textos.txt" dentro dela.')
        sys.exit(1)

    pastas.sort()
    print("Gerando %d vídeo(s)...\n" % len(pastas))
    for nome in pastas:
        print("→ %s" % nome)
        try:
            saida = processar_pasta(nome, cfg)
            if saida:
                print("   ✓ pronto: %s" % saida)
        except Exception as e:
            print("   [ERRO] %s" % e)
    print("\nConcluído!")


if __name__ == "__main__":
    main()
