#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Busca trilhas de fundo CC-licenciadas no Openverse (API pública).

Espelha o estilo de `pexels.py`: urllib + leitura opcional da chave em
`segredos.txt`.

Openverse NÃO exige chave para uso básico (acesso anônimo). O campo
`openverse_key=` em `segredos.txt` é reservado para acesso autenticado
(OAuth2 Bearer token), que costuma ter limites de requisição maiores.
Para obter um token: https://api.openverse.org/v1/#/auth (client credentials).

Contrato verificado (2026-09) do endpoint de áudio:
    GET https://api.openverse.org/v1/audio/?q=<QUERY>&page_size=<n>&format=json
    Resposta: {"result_count": int, "results": [ { ... } ]}

`format=json` é obrigatório: o CDN (Cloudflare) do Openverse cacheia a
resposta como HTML (browsable API do DRF) e ignora o header `Accept`.

Limites anônimos observados nos headers de resposta:
    x-ratelimit-limit-anon_burst:     20/min
    x-ratelimit-limit-anon_sustained: 200/day
(prefira cachear; a ladder de query abaixo faz 1-4 requisições por chamada)

Campos relevantes de cada hit em `results`:
    id              str  (UUID, ex.: "6a649dd1-3baa-4902-84c2-c0eaada1aece")
    title           str
    url             str  (URL direta do MP3 — usado como url_download)
    duration        int  *** em MILISSEGUNDOS *** (ex.: 76240 -> 76s)
    creator         str
    license         str  (código: "by", "by-nc-nd", "cc0", ...)
    license_version str  (ex.: "4.0")
    license_url     str
    attribution     str  (texto de atribuição pronto p/ exibir)
    tags            list[{"name": str, "accuracy": ..., ...}]

Todas as falhas de rede/HTTP viram `RuntimeError("Openverse audio falhou: ...")`
para permitir soft-fail no caller (vídeo sai sem áudio).

LICENÇAS: o Openverse agrega faixas sob várias licenças CC, inclusive
**não-comerciais** (`by-nc-*`) e **sem-derivados** (`*-nd`). Como os vídeos
podem ser monetizados, `buscar_opcoes` usa por padrão o filtro
`commercial,modification` (= CC BY / CC BY-SA / CC0 apenas; exclui NC e ND).
Se a busca filtrada não achar nada, há um fallback final sem filtro de
licença (qualquer CC) — nesse caso cada opção ainda traz os campos
`license` / `creator` para exibição/atribuição na UI.
"""

import os
import json
import urllib.request
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEGREDOS = os.path.join(BASE_DIR, "segredos.txt")

# Openverse recomenda um User-Agent descritivo (evita bloqueio de anônimos).
USER_AGENT = "seanettle-tiktok-video-maker/1.0 (Openverse audio search)"

AUDIO_BUSCA_URL = "https://api.openverse.org/v1/audio/"

# Prioriza música em vez de efeitos sonoros/ambiente.
CATEGORY_PADRAO = "music"
# Filtro de licença padrão: apenas licenças que permitem uso comercial E
# modificações, ou seja, CC BY, CC BY-SA e CC0 (exclui NC e ND).
# O Openverse aceita valores compostos separados por vírgula.
LICENSE_TYPE_PADRAO = "commercial,modification"


def ler_chave_openverse():
    """Lê 'openverse_key=...' de segredos.txt. Retorna None se ausente.

    O acesso básico ao Openverse não exige chave; este campo é reservado para
    acesso autenticado (OAuth2 Bearer token) com limites maiores.
    """
    try:
        with open(SEGREDOS, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha.startswith("openverse_key="):
                    return linha.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def _get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=25)


def _headers(chave=None):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    chave = chave if chave is not None else ler_chave_openverse()
    if chave:
        headers["Authorization"] = "Bearer %s" % chave
    return headers


def formatar_duracao(segundos):
    """Formata segundos como "M:SS" (ex.: 154 -> "2:34")."""
    try:
        total = int(round(float(segundos)))
    except (TypeError, ValueError):
        total = 0
    total = max(total, 0)
    return "%d:%02d" % (total // 60, total % 60)


def _ms_para_segundos(valor):
    """Openverse devolve `duration` em milissegundos -> converte p/ segundos."""
    try:
        ms = float(valor)
    except (TypeError, ValueError):
        return 0
    if ms < 0:
        ms = 0
    return int(round(ms / 1000.0))


def _formatar_licenca(hit):
    """Monta um rótulo curto e legível da licença ('CC BY-NC-ND 4.0')."""
    codigo = str(hit.get("license") or "").strip()
    versao = str(hit.get("license_version") or "").strip()
    if not codigo:
        return ""
    if codigo.lower() == "cc0":
        rotulo = "CC0"
    else:
        rotulo = "CC " + codigo.upper()
    return (rotulo + " " + versao).strip()


def _url_download(hit):
    """URL direta do MP3 (`url`), com fallback pro primeiro `alt_files` mp3."""
    url = hit.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    for alt in (hit.get("alt_files") or []):
        if not isinstance(alt, dict):
            continue
        filetype = str(alt.get("filetype") or "").lower()
        alt_url = alt.get("url")
        if filetype.startswith("mp3") and isinstance(alt_url, str) and alt_url.strip():
            return alt_url.strip()
    return ""


def _hit_para_opcao(hit):
    """Normaliza um hit do Openverse no dict esperado pelo app."""
    if not isinstance(hit, dict):
        return None

    hid = hit.get("id")
    if hid is None:
        return None
    hid = str(hid).strip()
    if not hid:
        return None

    url_download = _url_download(hit)
    if not url_download:
        return None

    duracao = _ms_para_segundos(hit.get("duration"))
    titulo = str(hit.get("title") or "").strip() or ("Faixa %s" % hid[:8])

    tags = []
    for t in (hit.get("tags") or []):
        nome = (t.get("name") if isinstance(t, dict) else t) or ""
        nome = str(nome).strip()
        if nome:
            tags.append(nome)

    return {
        "id": hid,
        "title": titulo,
        "duration": duracao,
        "duration_str": formatar_duracao(duracao),
        "url_download": url_download,
        "preview_url": "/api/audio/preview/%s" % urllib.parse.quote(hid, safe=""),
        "tags": tags,
        "creator": str(hit.get("creator") or "").strip(),
        "license": _formatar_licenca(hit),
    }


def _montar_url(query, n, category, license_type):
    # `format=json` é obrigatório: o Cloudflare do Openverse cacheia a resposta
    # como HTML (browsable API) e ignora o header `Accept`.
    params = {"q": query, "page_size": max(int(n), 1), "format": "json"}
    if category:
        params["category"] = category
    if license_type:
        params["license_type"] = license_type
    return AUDIO_BUSCA_URL + "?" + urllib.parse.urlencode(params)


def _consultar(query, n, chave, category, license_type):
    """Faz uma requisição e devolve a lista crua de `results` (ou [])."""
    url = _montar_url(query, n, category, license_type)
    try:
        resposta = _get(url, _headers(chave))
        dados = json.loads(resposta.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError("Openverse audio falhou: %s" % e)
    resultados = dados.get("results") or []
    return resultados if isinstance(resultados, list) else []


def _variantes(query):
    """Variantes progressivamente mais curtas da query.

    O `q` do Openverse é bastante restritivo com frases longas (as buscas de
    tema têm 4 palavras e costumam devolver 0). Encurtar recupera resultados.
    """
    palavras = [p for p in (query or "").split() if p]
    vistas = []
    for k in (len(palavras), 3, 2):
        if 1 <= k <= len(palavras):
            variante = " ".join(palavras[:k])
            if variante not in vistas:
                vistas.append(variante)
    return vistas


def _para_opcoes(resultados, n):
    """Normaliza hits do Openverse em opções (até N)."""
    opcoes = []
    for hit in resultados:
        opcao = _hit_para_opcao(hit)
        if opcao:
            opcoes.append(opcao)
        if len(opcoes) >= n:
            break
    return opcoes


def buscar_opcoes(query, n=5, chave=None, license_type=LICENSE_TYPE_PADRAO):
    """Busca até N trilhas CC no Openverse e retorna lista de dicts.

    Shape de cada item (server.py depende disso):
        {"id": str, "title": str, "duration": int (s), "duration_str": "M:SS",
         "url_download": str, "preview_url": "/api/audio/preview/<id>",
         "tags": [str], "creator": str, "license": str}

    Licenças: por padrão usa `license_type="commercial,modification"` (CC BY /
    CC BY-SA / CC0), que exclui as variantes NC (não-comercial) e ND
    (sem-derivados) — seguro para conteúdo que pode ser monetizado. O filtro é
    mantido em TODOS os passos da ladder de busca. Se a ladder inteira voltar
    vazia, faz UMA última busca (com a variante mais curta da query) sem filtro
    de licença (qualquer CC), para não zerar temas que não têm trilha
    comercial. Passe `license_type=None` para desabilitar o filtro desde o
    início.

    Estratégia (ladder): tenta a query completa com `category=music`; se vier
    vazia, encurta progressivamente (3 e 2 primeiras palavras) e, por fim,
    tenta a query completa sem categoria — sempre com o mesmo filtro de
    licença. Retorna [] se nada for encontrado. Levanta RuntimeError em falha
    de rede.
    """
    query = (query or "").strip()
    if not query:
        return []

    # Ladder com o filtro de licença mantido em TODOS os passos.
    tentativas = [(v, CATEGORY_PADRAO) for v in _variantes(query)]
    tentativas.append((query, ""))  # sem categoria, ainda com filtro de licença

    for variante, categoria in tentativas:
        opcoes = _para_opcoes(
            _consultar(variante, n, chave, categoria, license_type), n)
        if opcoes:
            return opcoes

    # Fallback final: UMA tentativa sem filtro de licença (qualquer CC).
    # Usa a variante MAIS CURTA (a mais provável de ter resultado, já que o
    # `q` do Openverse é restritivo com frases longas).
    if license_type:
        variante_final = _variantes(query)[-1]
        return _para_opcoes(
            _consultar(variante_final, n, chave, CATEGORY_PADRAO, None), n)
    return []


def baixar_track(url, destino=None):
    """Baixa os bytes do MP3.

    Se `destino` for um caminho, grava lá e retorna o caminho.
    Caso contrário, retorna os bytes.
    """
    if not url:
        raise RuntimeError("Openverse audio falhou: URL de download vazia.")

    try:
        dados = _get(url, {"User-Agent": USER_AGENT}).read()
    except Exception as e:
        raise RuntimeError("Openverse audio falhou: %s" % e)

    if destino:
        pasta = os.path.dirname(os.path.abspath(destino))
        if pasta:
            os.makedirs(pasta, exist_ok=True)
        with open(destino, "wb") as f:
            f.write(dados)
        return destino
    return dados
