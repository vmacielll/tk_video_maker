#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pipeline automático: tema -> video local.

Uso:
    python3 auto_gerar.py <tema> [--out saida_auto/]

Pipeline:
    1. Carrega tema de temas.py (frases padrão, legenda padrão, busca Pexels, CTA)
    2. Tenta gerar frases frescas com gemini.py (Groq); cai pras padrão se falhar
    3. Tenta gerar legenda fresca com gemini.py; cai pra padrão se falhar
    4. Busca N imagens de fundo no Pexels (1 por tela)
    5. Renderiza o .mp4 via nucleo.gerar_video()
    6. Salva a legenda em .txt ao lado do .mp4
    7. Imprime JSON com metadados do vídeo gerado

Saída (stdout, JSON):
    {
        "tema": "lei da atracao",
        "arquivo_local": "/abs/path/saida_auto/video_20260909_142300.mp4",
        "legenda_local": "/abs/path/saida_auto/video_20260909_142300.txt",
        "legenda": "...",
        "frases": ["frase 1", "frase 2", ...],
        "fonte_frases": "groq",
        "fonte_legenda": "groq",
        "video_made_with_ai": true,
        "gerado_em": "2026-09-09T14:23:00+00:00"
    }

NÃO ALTERAR gerar.py nem server.py — esse script é independente.

Obs.: o módulo b2_storage.py continua no repo pra uso manual
(via REPL ou outros scripts), mas auto_gerar.py não sobe mais o .mp4
pro B2 automaticamente.
"""

import argparse
import json
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import gemini
import nucleo
import openverse_audio
import pexels
import temas
from tiktok_auto_post import tiktok_auth


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


def _resolve_audio_path(
    audio_flag,
    tema_obj,
    searcher=None,
    downloader=None,
):
    """Return the path to a downloaded background audio file, or None.

    When `audio_flag` is not "auto", returns None immediately without
    contacting the audio source. When "auto", searches for tracks, picks
    one at random, downloads it to a temp file, and returns the path.
    Soft-fails to None on any network or search error.
    """
    if audio_flag != "auto":
        return None

    if searcher is None:
        searcher = openverse_audio.buscar_opcoes
    if downloader is None:
        downloader = openverse_audio.baixar_track

    busca_audio = (
        tema_obj.get("musica_busca")
        or tema_obj.get("busca")
        or "ambient hopeful inspirational background"
    )

    try:
        opcoes_audio = searcher(busca_audio, n=5)
    except Exception as e:
        _stderr(f"       ! audio search failed (soft): {e}")
        return None

    if not opcoes_audio:
        return None

    pick = random.choice(opcoes_audio)
    tmp_audio = tempfile.mktemp(suffix=".mp3")
    downloader(pick["url_download"], tmp_audio)
    return tmp_audio


def _pre_check_tokens(tokens_path):
    """DEPRECATED: use ``tiktok_auth.tiktok_status`` directly.

    Kept as a thin wrapper for backward compatibility with existing tests; new
    code should call ``tiktok_auth.tiktok_status(tokens_path)`` directly so the
    single source of truth lives in ``tiktok_auto_post/tiktok_auth.py``.
    """
    return tiktok_auth.tiktok_status(tokens_path)


_DEFAULT_POSTAR_BIN = (
    pathlib.Path(__file__).resolve().parent / "tiktok_auto_post" / "tiktok_postar.py"
)


def _invoke_publish_subprocess(
    video_path,
    caption=None,
    *,
    postar_bin=None,
    env=None,
    timeout=180,
):
    """Invoke tiktok_postar.py as a subprocess and return the publish block.

    Maps the subprocess exit code to a normalized error_type:
    - 0: success (publish_id parsed from stdout JSON)
    - 1: user error
    - 2: auth error
    - 3: upload error
    - other: upload (fallback)

    `postar_bin` overrides the default postar script path (useful for tests).
    `env` is merged on top of os.environ for the subprocess.
    """
    if postar_bin is None:
        postar_bin = os.environ.get("TIKTOK_POSTAR_BIN", str(_DEFAULT_POSTAR_BIN))

    cmd = [sys.executable, str(postar_bin), str(video_path)]
    if caption:
        cmd += ["--caption", caption]

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=full_env,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "attempted": True,
            "success": False,
            "publish_id": None,
            "error": "tiktok_postar timed out",
            "error_type": "upload",
        }
    except Exception as e:
        return {
            "attempted": True,
            "success": False,
            "publish_id": None,
            "error": f"failed to invoke tiktok_postar: {e}",
            "error_type": "upload",
        }

    if proc.returncode == 0:
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {
                "attempted": True,
                "success": False,
                "publish_id": None,
                "error": "tiktok_postar returned non-JSON on success: " + (proc.stdout[:200] or ""),
                "error_type": "upload",
            }
        return {
            "attempted": True,
            "success": True,
            "publish_id": payload.get("publish_id"),
            "error": None,
            "error_type": None,
        }

    if proc.returncode == 1:
        error_type = "user"
    elif proc.returncode == 2:
        error_type = "auth"
    else:
        error_type = "upload"

    err = (proc.stderr or proc.stdout or "").strip()
    if not err:
        err = f"tiktok_postar exited with code {proc.returncode}"
    return {
        "attempted": True,
        "success": False,
        "publish_id": None,
        "error": err,
        "error_type": error_type,
    }


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
    ap.add_argument("--cta", default=None,
                    help="CTA customizado (override do tema)")
    ap.add_argument("--publish", choices=["yes", "no"], default="no",
                    help="Post the generated video to TikTok automatically (default: no)")
    ap.add_argument("--audio", choices=["auto", "off"], default="off",
                    help="Whether to embed audio (Openverse auto-pick) in the video (default: off)")
    args = ap.parse_args()

    # Pre-check TikTok tokens when --publish=yes. Bail out before doing any
    # expensive work (Groq / Pexels / ffmpeg) so the user doesn't wait 30s
    # just to discover the OAuth flow is missing.
    if args.publish == "yes":
        pre = tiktok_auth.tiktok_status(tiktok_auth.TOKENS_PATH)
        if not pre["configured"] or not pre["scope_ok"]:
            block = {
                "attempted": True,
                "success": False,
                "publish_id": None,
                "error": (
                    f"TikTok tokens not configured "
                    f"(configured={pre['configured']}, scope_ok={pre['scope_ok']}, "
                    f"expires_at={pre['expires_at']})"
                ),
                "error_type": "auth",
            }
            result = {
                "tema": args.tema,
                "publish": block,
                "gerado_em": datetime.now(timezone.utc).isoformat(),
            }
            _stderr(f"       ! pre-check failed: {block['error']}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(2)

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
    _stderr(f"[1/4] Frases (tema={tema_nome!r})...")
    frases, fonte_frases = _resolver_frases(tema_obj, tema_nome, cta)
    _stderr(f"       {len(frases)} frases ({fonte_frases})")

    _stderr("[2/4] Legenda...")
    legenda, fonte_legenda = _resolver_legenda(tema_obj, tema_nome, frases, cta)
    _stderr(f"       {len(legenda)} chars ({fonte_legenda})")

    # 3) Pexels
    n_fundos = len(frases)
    _stderr(f"[3/4] Pexels (n={n_fundos}, query={busca!r})...")
    try:
        imagens_bytes = pexels.buscar_fundos(busca, n_fundos)
        if not imagens_bytes:
            raise RuntimeError("Pexels retornou 0 imagens")
    except Exception as e:
        raise SystemExit(f"Falha ao buscar fundos no Pexels: {e}")
    _stderr(f"       {len(imagens_bytes)} imagens")

    # 3b) Música de fundo (controlled by --audio; default off = no audio)
    if args.audio == "auto":
        _stderr("[3b/4] Música (Openverse audio)...")
        audio_path = _resolve_audio_path(args.audio, tema_obj)
    else:
        _stderr("[3b/4] Música: off (default)")
        audio_path = None

    # 4) Render do vídeo
    _stderr("[4/4] Renderizando .mp4 (pode levar ~30s)...")
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
            "audio_path": audio_path,
            "volume_audio": 0.5,
            "fade_in_audio": 0.4,
            "fade_out_audio": 0.8,
        }
        caminho_video = nucleo.gerar_video(bgs_paths, frases, opcoes)

        caminho_legenda = os.path.join(args.out, nome + ".txt")
        with open(caminho_legenda, "w", encoding="utf-8") as f:
            f.write(legenda + "\n")
        _stderr(f"       vídeo:     {caminho_video}")
        _stderr(f"       legenda:   {caminho_legenda}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        if audio_path:
            try:
                os.remove(audio_path)
            except OSError:
                pass

    # 5) Output JSON
    result = {
        "tema": tema_nome,
        "arquivo_local": caminho_video,
        "legenda_local": caminho_legenda,
        "legenda": legenda,
        "frases": frases,
        "fonte_frases": fonte_frases,
        "fonte_legenda": fonte_legenda,
        "video_made_with_ai": True,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }
    publish_block = None
    if args.publish == "yes":
        _stderr("[5/5] Postando no TikTok...")
        publish_block = _invoke_publish_subprocess(
            caminho_video,
            caption=legenda,
        )
        result["publish"] = publish_block
        if publish_block["success"]:
            _stderr(f"       postado: {publish_block['publish_id']}")
        else:
            _stderr(f"       ! falha ({publish_block['error_type']}): {publish_block['error']}")
    # stdout = JSON puro
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if publish_block and not publish_block["success"]:
        if publish_block["error_type"] == "auth":
            sys.exit(2)
        if publish_block["error_type"] == "user":
            sys.exit(1)
        sys.exit(3)


if __name__ == "__main__":
    main()
