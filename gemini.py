#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera textos (frases + legenda) via API do Groq (API compatível com OpenAI).

Modelo gratuito com limite alto (~14k requests/dia).
"""

import os
import json
import urllib.request
import urllib.error

from nucleo import tirar_emoji

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEGREDOS = os.path.join(BASE_DIR, "segredos.txt")

# User-Agent de navegador: o Cloudflare do Groq bloqueia o urllib padrão (erro 1010).
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Modelo gratuito do Groq. qwen3.8 respondeu mais consistente que o gpt-oss
# (que às vezes retorna vazio). Confirme a disponibilidade com GET /openai/v1/models.
MODELO = "qwen/qwen3.8-27b"


def ler_chave():
    try:
        with open(SEGREDOS, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha.startswith("groq_key="):
                    return linha.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def _chamar(prompt, temperatura=0.9):
    chave = ler_chave()
    if not chave:
        raise RuntimeError("Chave do Groq não encontrada (segredos.txt, campo groq_key=).")
    url = "https://api.groq.com/openai/v1/chat/completions"
    payload = {
        "model": MODELO,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperatura,
        "max_tokens": 600,
    }
    ultimo_erro = None
    for tentativa in range(3):
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": USER_AGENT,
                                              "Authorization": "Bearer " + chave})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))
            texto = resp["choices"][0]["message"].get("content") or ""
            texto = texto.strip()
            if texto:
                return texto
            ultimo_erro = RuntimeError("Groq retornou resposta vazia.")
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", "replace")[:300]
            ultimo_erro = RuntimeError("HTTP %s: %s" % (e.code, corpo))
            if e.code in (400, 401, 403, 404):
                break  # erro definitivo, não faz sentido tentar de novo
        except Exception as e:
            ultimo_erro = RuntimeError(str(e))
    if ultimo_erro:
        raise ultimo_erro
    return ""


def gerar_frases(tema, cta=None):
    if cta:
        cta_linha = 'A 6ª frase é EXATAMENTE: "%s".' % tirar_emoji(cta)
    else:
        cta_linha = 'A 6ª frase é uma chamada para comentar (ex.: "Comenta EU ACEITO se você acredita" ou "Comenta teu signo").'
    prompt = (
        'Escreva 7 frases curtas para um vídeo de TikTok no nicho de misticismo, '
        'espiritualidade e lei da atração, sobre o tema/formato: "%s".\n\n'
        "Regras:\n"
        "- Uma frase por linha, exatamente 7 frases.\n"
        '- Frases curtas (máximo 10 palavras), em português do Brasil, usando "você" (nunca "tu").\n'
        '- Se o tema for sobre fatos, curiosidades, signos, números ou origens: comece com um gancho de curiosidade (ex.: "Você sabia que...?") e entregue a informação/fato nas frases seguintes.\n'
        "- Se o tema for mensagem motivacional: use tom íntimo e acolhedor.\n"
        "- As 5 primeiras frases são o conteúdo do vídeo.\n"
        "%s\n"
        '- A 7ª frase é uma chamada para seguir (ex.: "Me segue para mais").\n'
        "- Sem emojis, sem hashtags, sem numeração.\n\n"
        "Responda apenas as 7 frases, uma por linha."
    ) % (tema, cta_linha)
    texto = _chamar(prompt)
    frases = [l.strip() for l in texto.splitlines() if l.strip()]
    frases = [l.lstrip("0123456789.-) ") for l in frases]
    frases = [l for l in frases if l]
    return frases[:7]


def gerar_legenda(tema, frases, cta=None):
    frases_txt = " | ".join(frases[:5]) if frases else ""
    if cta:
        cta_linha = 'A chamada para comentar/engajar deve ser: "%s".' % cta
    else:
        cta_linha = 'A chamada deve ser "Comenta EU ACEITO" e "me segue para mais".'
    prompt = (
        'Escreva uma legenda curta para TikTok, em português, para um vídeo '
        'sobre o tema: "%s".\n\n'
        "As frases do vídeo são: %s\n\n"
        "A legenda deve ter:\n"
        "- Uma frase de abertura chamativa\n"
        "%s\n"
        "- 5 a 7 hashtags relevantes (com #, sem acento nas hashtags)\n"
        "- Pode usar emojis.\n\n"
        "Responda apenas a legenda."
    ) % (tema, frases_txt, cta_linha)
    return _chamar(prompt, temperatura=0.8)
