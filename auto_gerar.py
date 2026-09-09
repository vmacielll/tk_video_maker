#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pipeline automático: tema -> video -> B2 -> URL assinada.

Uso:
    python3 auto_gerar.py <tema> [--out saida_auto/] [--valid-hours 24] [--no-upload]

Pipeline:
    1. Carrega tema de temas.py (frases padrão, legenda padrão, busca Pexels, CTA)
    2. Tenta gerar frases frescas com gemini.py (Groq); cai pras padrão se falhar
    3. Tenta gerar legenda fresca com gemini.py; cai pra padrão se falhar
    4. Busca N imagens de fundo no Pexels (1 por tela)
    5. Renderiza o .mp4 via nucleo.gerar_video()
    6. Salva a legenda em .txt ao lado do .mp4
    7. Sobe o .mp4 pro Backblaze B2 (bucket privado) via b2_storage
    8. Gera URL HTTPS assinada (default 24h) pro TikTok fetch via pull_from_url
    9. Imprime JSON com metadados (consumível pelo próximo passo: Postiz/Hermes)

Saída (stdout, JSON):
    {
        "tema": "lei da atracao",
        "arquivo_local": "/abs/path/saida_auto/video_20260909_142300.mp4",
        "legenda_local": "/abs/path/saida_auto/video_20260909_142300.txt",
        "legenda": "...",
        "frases": ["frase 1", "frase 2", ...],
        "b2_key": "videos/2026-09-09/video_20260909_142300.mp4",
        "b2_url": "https://f005.backblazeb2.com/file/tk-video-maker/...?Authorization=...",
        "url_expira_em": "2026-09-10T14:23:00+00:00",
        "video_made_with_ai": true,
        "gerado_em": "2026-09-09T14:23:00+00:00"
    }

NÃO ALTERAR gerar.py nem server.py — esse script é independente.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta

import gemini
import nucleo
import pexels
import temas
import b2_storage


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAIDA_AUTO = os.path.join(BASE_DIR, "saida_auto")


def _hex_para_rgb(hex_str):
    """Converte "#d4af37" -> (212, 175, 55). Cai pra COR_PADRAO se inválido."""
    s = (hex_str or "").strip().lstrip("#")
    if len(s) == 6:
        try:
            return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    return nucleo.COR_PADRAO


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _stderr(msg):
    """Log de progresso em stderr; stdout fica reservado pro JSON final."""
    print(msg, file=sys.stderr, flush=True)


def _legenda_curta(tema_nome, frases):
    """Gera um caption curto de fallback (caso o Groq falhe pra legenda)."""
    return (
        f"{tema_nome.capitalize()} — assista até o fim e me segue pra mais ✨\n\n"
        + " | ".join(frases[:3])
    )


def _parse_json_payload(stdout_text):
    """Extrai o último JSON object do stdout (ignora warnings/lines de debug)."""
    txt = stdout_text.strip()
    if not txt:
        return None
    # se termina com }, parse direto
    if txt.endswith("}"):
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            pass
    # fallback: pega do último "{" até o final
    start = txt.rfind("{")
    if start < 0:
        return None
    candidato = txt[start:]
    try:
        return json.loads(candidato)
    except json.JSONDecodeError:
        return None


def _resolver_frases(tema_obj, tema_nome, cta):
    """Tenta gerar frases com Groq; cai pras do tema se a chamada falhar."""
    try:
        f = gemini.gerar_frases(tema_nome, cta)
        if len(f) >= 5:
            return f, "groq"
        _stderr(f"       ! Groq devolveu só {len(f)} frases, usando fallback do tema")
    except Exception as e:
        _stderr(f"       ! Groq falhou: {e}")
    return list(tema_obj["frases"]), "tema"


def _resolver_legenda(tema_obj, tema_nome, frases, cta):
    """Tenta gerar legenda com Groq; cai pra padrão do tema."""
    try:
        return gemini.gerar_legenda(tema_nome, frases[:5], cta), "groq"
    except Exception as e:
        _stderr(f"       ! Groq falhou: {e}")
    return _legenda_curta(tema_nome, frases), "fallback"


def main():
    ap = argparse.ArgumentParser(description="Gera vídeo de um tema + sobe pro B2")
    ap.add_argument("tema", help="Nome do tema (chave em temas.py, ex: 'lei da atracao')")
    ap.add_argument("--out", default=SAIDA_AUTO,
                    help=f"Diretório de saída (default: {SAIDA_AUTO})")
    ap.add_argument("--valid-hours", type=int, default=24,
                    help="Validade da URL B2 em horas (default: 24)")
    ap.add_argument("--cta", default=None,
                    help="CTA customizado (override do tema)")
    ap.add_argument("--no-upload", action="store_true",
                    help="Gera vídeo local mas NÃO sobe pro B2")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    tema_nome = args.tema.strip().lower()
    tema_obj = temas.obter_tema(tema_nome)
    if tema_obj is None:
        raise SystemExit(
            f"Tema '{args.tema}' não encontrado.\n"
            f"Disponíveis: {', '.join(temas.listar_temas())}"
        )

    busca = tema_obj["busca"]
    cta = args.cta or temas.obter_cta(tema_nome)

    # 1+2) Frases + legenda via Groq (com fallback)
    _stderr(f"[1/5] Frases (tema={tema_nome!r})...")
    frases, fonte_frases = _resolver_frases(tema_obj, tema_nome, cta)
    _stderr(f"       {len(frases)} frases ({fonte_frases})")

    _stderr("[2/5] Legenda...")
    legenda, fonte_legenda = _resolver_legenda(tema_obj, tema_nome, frases, cta)
    _stderr(f"       {len(legenda)} chars ({fonte_legenda})")

    # 3) Pexels
    n_fundos = len(frases)
    _stderr(f"[3/5] Pexels (n={n_fundos}, query={busca!r})...")
    try:
        imagens_bytes = pexels.buscar_fundos(busca, n_fundos)
        if not imagens_bytes:
            raise RuntimeError("Pexels retornou 0 imagens")
    except Exception as e:
        raise SystemExit(f"Falha ao buscar fundos no Pexels: {e}")
    _stderr(f"       {len(imagens_bytes)} imagens")

    # 4) Render do vídeo
    _stderr("[4/5] Renderizando .mp4 (pode levar ~30s)...")
    tmpdir = tempfile.mkdtemp(prefix="auto_gerar_")
    try:
        bgs_paths = []
        for i, img_bytes in enumerate(imagens_bytes[:n_fundos]):
            p = os.path.join(tmpdir, f"bg_{i}.jpg")
            with open(p, "wb") as f:
                f.write(img_bytes)
            bgs_paths.append(p)

        stamp = _stamp()
        nome = f"video_{stamp}"
        opcoes = {
            "duracao": nucleo.DURACAO_PADRAO,
            "fade": nucleo.FADE_PADRAO,
            "fonte": nucleo.FONTE_PADRAO,
            "cor": nucleo.COR_PADRAO,
            "escurecer": nucleo.ESCURECER_PADRAO,
            "tamanho": 1.0,
            "template": nucleo.TEMPLATE_PADRAO,
            "cor_destaque": _hex_para_rgb(tema_obj.get("cor")),
            "nome": nome,
            "saida_dir": args.out,
        }
        caminho_video = nucleo.gerar_video(bgs_paths, frases, opcoes)

        caminho_legenda = os.path.join(args.out, nome + ".txt")
        with open(caminho_legenda, "w", encoding="utf-8") as f:
            f.write(legenda + "\n")
        _stderr(f"       vídeo:     {caminho_video}")
        _stderr(f"       legenda:   {caminho_legenda}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    # 5) Upload pro B2
    b2_key = f"videos/{datetime.now().strftime('%Y-%m-%d')}/{nome}.mp4"
    b2_url = None
    url_expira_em = None
    if args.no_upload:
        _stderr("[5/5] Upload pro B2 pulado (--no-upload)")
    else:
        _stderr(f"[5/5] Subindo pro B2 (key={b2_key})...")
        b2 = b2_storage.B2Storage()
        b2.upload(b2_key, caminho_video, content_type="video/mp4")
        b2_url = b2.get_download_url(b2_key, valid_seconds=args.valid_hours * 3600)
        url_expira_em = (
            datetime.now(timezone.utc) + timedelta(hours=args.valid_hours)
        ).isoformat()
        _stderr(f"       URL gerada ({len(b2_url)} chars)")

    # Output JSON pro próximo passo (Hermes/Postiz)
    result = {
        "tema": tema_nome,
        "arquivo_local": caminho_video,
        "legenda_local": caminho_legenda,
        "legenda": legenda,
        "frases": frases,
        "fonte_frases": fonte_frases,
        "fonte_legenda": fonte_legenda,
        "b2_key": b2_key if not args.no_upload else None,
        "b2_url": b2_url,
        "url_expira_em": url_expira_em,
        "video_made_with_ai": True,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }
    # CRÍTICO: stdout = JSON puro (Hermes/Postiz script vão fazer parse)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
