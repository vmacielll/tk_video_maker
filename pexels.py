#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Busca imagens de fundo gratuitas no Pexels (API)."""

import os
import json
import random
import urllib.request
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEGREDOS = os.path.join(BASE_DIR, "segredos.txt")

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def ler_chave():
    try:
        with open(SEGREDOS, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha.startswith("pexels_key="):
                    return linha.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=25)


def buscar_fundo(query, chave=None, orientacao="portrait"):
    """Busca uma foto no Pexels pela query e retorna os bytes (JPEG).

    Retorna None se não encontrar nada. Escolhe uma foto aleatória entre
    as primeiras do resultado pra variar o fundo a cada geração.
    """
    chave = chave or ler_chave()
    if not chave:
        raise RuntimeError("Chave do Pexels não encontrada (crie segredos.txt).")

    url = ("https://api.pexels.com/v1/search?query=%s&per_page=6&orientation=%s"
           % (urllib.parse.quote(query), orientacao))
    headers = {"Authorization": chave, "User-Agent": USER_AGENT, "Accept": "application/json"}
    dados = json.loads(_get(url, headers).read().decode("utf-8"))
    fotos = dados.get("photos", [])
    if not fotos:
        return None

    foto = random.choice(fotos)
    src = foto["src"]
    img_url = src.get("large2x") or src.get("large") or src["original"]
    return _get(img_url, {"User-Agent": USER_AGENT}).read()


def buscar_fundos(query, n=7, chave=None, orientacao="portrait", page=1):
    """Busca N fotos DIFERENTES do Pexels (mesmo tema) e retorna uma lista de bytes.

    `page` avança a paginação do Pexels (para buscar imagens novas sem repetir).
    Retorna uma lista vazia se não encontrar nada.
    """
    chave = chave or ler_chave()
    if not chave:
        raise RuntimeError("Chave do Pexels não encontrada (crie segredos.txt).")

    per_page = min(max(n * 2, 10), 80)
    url = ("https://api.pexels.com/v1/search?query=%s&per_page=%d&orientation=%s&page=%d"
           % (urllib.parse.quote(query), per_page, orientacao, page))
    headers = {"Authorization": chave, "User-Agent": USER_AGENT, "Accept": "application/json"}
    dados = json.loads(_get(url, headers).read().decode("utf-8"))
    fotos = dados.get("photos", [])
    if not fotos:
        return []

    random.shuffle(fotos)
    resultado = []
    for foto in fotos[:n]:
        src = foto["src"]
        img_url = src.get("large2x") or src.get("large") or src["original"]
        resultado.append(_get(img_url, {"User-Agent": USER_AGENT}).read())
    return resultado
