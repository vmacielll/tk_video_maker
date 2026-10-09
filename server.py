#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Servidor web simples do gerador de vídeos.

Roda o frontend (pasta web/) e expõe a API:
    POST /api/gerar   -> gera um vídeo (JSON, imagem em base64)
    GET  /api/videos  -> lista os vídeos gerados
    GET  /videos/<n>  -> serve o arquivo .mp4
    GET  /api/audio/buscar?tema=X|query=Y -> opções de trilha (Pixabay)
    GET  /api/audio/preview/<id>           -> serve o MP3 (HTTP Range)

Uso:
    python3 server.py            (porta 8000)
    python3 server.py 8080       (porta customizada)
"""

import os
import io
import json
import time
import atexit
import shutil
import random
import base64
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qsl, unquote

import nucleo
import pexels
import temas
import gemini
import openverse_audio
from tiktok_auto_post import tiktok_auth
import job_store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
SAIDA_WEB = os.path.join(BASE_DIR, "saida_web")

# Sessão de áudio: temp dir criado no load.
#   audio_url_map: track_id -> url_download (metadados, sem baixar)
#   audio_cache:   track_id -> caminho local (baixado sob demanda)
AUDIO_TEMP_DIR = tempfile.mkdtemp(prefix="audio_sess_")
audio_url_map = {}
audio_cache = {}


def _limpar_audio_temp():
    shutil.rmtree(AUDIO_TEMP_DIR, ignore_errors=True)


atexit.register(_limpar_audio_temp)

TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


# Job store for the publish flow (issue #4). In-memory; reboot loses jobs.
# Background GC evicts jobs older than the TTL (1h) every 5min.
JOB_STORE = job_store.JobStore(ttl_seconds=3600, gc_interval_seconds=300)
JOB_STORE.start_gc()


def _stop_job_store_gc():
    try:
        JOB_STORE.stop_gc()
    except Exception:
        pass


atexit.register(_stop_job_store_gc)


def parse_cor(s):
    s = (s or "").strip()
    if s.startswith("#"):
        s = s[1:]
        if len(s) == 6:
            try:
                return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                pass
    partes = [p.strip() for p in s.split(",")]
    if len(partes) == 3:
        try:
            return tuple(int(p) for p in partes)
        except ValueError:
            pass
    return nucleo.COR_PADRAO


def decodificar_imagem(valor):
    if "," in valor and valor.split(",", 1)[0].startswith("data:"):
        valor = valor.split(",", 1)[1]
    return base64.b64decode(valor)


def _num(dados, campo, padrao):
    try:
        return float(dados.get(campo, padrao))
    except (TypeError, ValueError):
        return float(padrao)


def escala_de(dados):
    try:
        return max(0.3, min(2.0, float(dados.get("tamanho", 100)) / 100.0))
    except (TypeError, ValueError):
        return 1.0


def resolve_template(dados, auto=True):
    """Retorna um id de template válido.

    Ausente/vazio/"auto"/inválido -> sorteia (auto=True) ou usa o padrão.
    """
    t = (dados.get("template") or "").strip().lower()
    if not t or t == "auto" or t not in nucleo.TEMPLATES:
        return nucleo.sortear_template() if auto else nucleo.TEMPLATE_PADRAO
    return t


def resolve_cor_destaque(dados):
    v = dados.get("cor_destaque")
    if v:
        return parse_cor(v)
    return nucleo.COR_DESTAQUE_PADRAO


def listar_videos():
    os.makedirs(SAIDA_WEB, exist_ok=True)
    itens = []
    for nome in os.listdir(SAIDA_WEB):
        if nome.endswith(".mp4"):
            caminho = os.path.join(SAIDA_WEB, nome)
            itens.append((os.path.getmtime(caminho), nome))
    itens.sort(reverse=True)
    return [{"nome": n, "url": "/videos/" + n} for _, n in itens]


def _nome_arquivo_audio(track_id):
    """Nome de arquivo seguro pra um id (UUID) do Openverse."""
    seguro = "".join(
        c if (c.isalnum() or c in "._-") else "_" for c in str(track_id))
    return "track_" + seguro + ".mp3"


def _baixar_para_cache(track_id, url):
    """Baixa o MP3 sob demanda e registra em `audio_cache`.

    Retorna o caminho local, ou None se a URL não existir / o download falhar.
    """
    if not url:
        return None
    try:
        track_id = str(track_id)
        destino = os.path.join(AUDIO_TEMP_DIR, _nome_arquivo_audio(track_id))
        if not os.path.exists(destino):
            openverse_audio.baixar_track(url, destino)
        audio_cache[track_id] = destino
        return destino
    except Exception:
        return None


def _buscar_audio(query, n=5):
    """Busca até N trilhas no Openverse — SÓ metadados, sem baixar nada.

    Popula `audio_url_map` (id -> url_download) pra que o preview e o `/api/gerar`
    baixem sob demanda. A resposta fica rápida (sem esperar os MP3).
    """
    opcoes = openverse_audio.buscar_opcoes(query, n=n)
    for op in opcoes:
        try:
            audio_url_map[str(op["id"])] = op["url_download"]
        except (KeyError, TypeError):
            continue
    return opcoes


def _busca_audio_do_payload(dados):
    """Resolve a query de música a partir do payload (tema ou busca direta)."""
    tema = (dados.get("tema") or "").strip()
    if tema:
        tema_obj = temas.obter_tema(tema)
        if tema_obj:
            return (tema_obj.get("musica_busca") or tema_obj.get("busca") or "").strip()
    return (dados.get("musica_busca") or dados.get("busca") or "").strip()


def _resolver_audio_path(audio_id, query):
    """Devolve o caminho local do áudio escolhido (baixando sob demanda), ou None.

    1) Se já está em `audio_cache`, usa.
    2) Se a URL é conhecida (`audio_url_map`), baixa e cacheia.
    3) Senão, re-busca (`_buscar_audio`) pra refrescar os mapas e tenta o id;
       se o id sumiu, cai num pick aleatório do top-5.
    """
    if audio_id is None:
        return None
    audio_id = str(audio_id)

    caminho = audio_cache.get(audio_id)
    if caminho and os.path.exists(caminho):
        return caminho

    url = audio_url_map.get(audio_id)
    if url:
        caminho = _baixar_para_cache(audio_id, url)
        if caminho:
            return caminho

    try:
        opcoes = _buscar_audio(query, n=5)
    except Exception:
        return None
    if not opcoes:
        return None
    for op in opcoes:
        if str(op["id"]) == audio_id:
            return _baixar_para_cache(str(op["id"]), op["url_download"])
    pick = random.choice(opcoes)
    return _baixar_para_cache(str(pick["id"]), pick["url_download"])


class Handler(BaseHTTPRequestHandler):
    server_version = "GeradorVideos/1.0"

    def log_message(self, format, *args):
        pass  # silencioso

    # ---------- utilidades ----------
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _arquivo(self, caminho, tipo):
        try:
            with open(caminho, "rb") as f:
                dados = f.read()
        except FileNotFoundError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def _servir_mp3(self, caminho):
        """Serve um .mp3 com suporte a HTTP Range (206 Partial Content)."""
        try:
            tamanho = os.path.getsize(caminho)
        except OSError:
            self.send_error(404)
            return
        cabecalho = self.headers.get("Range") or ""
        try:
            with open(caminho, "rb") as f:
                if cabecalho.startswith("bytes=") and tamanho > 0:
                    spec = cabecalho[len("bytes="):].split(",")[0].strip()
                    inicio_s, _, fim_s = spec.partition("-")
                    if inicio_s == "":
                        # Sufixo: últimos N bytes.
                        n_ult = int(fim_s or 0)
                        inicio = max(tamanho - n_ult, 0)
                        fim = tamanho - 1
                    else:
                        inicio = int(inicio_s)
                        fim = int(fim_s) if fim_s else tamanho - 1
                    if inicio > fim or inicio >= tamanho:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % tamanho)
                        self.end_headers()
                        return
                    fim = min(fim, tamanho - 1)
                    f.seek(inicio)
                    dados = f.read(fim - inicio + 1)
                    self.send_response(206)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Range",
                                     "bytes %d-%d/%d" % (inicio, fim, tamanho))
                    self.send_header("Content-Length", str(len(dados)))
                    self.end_headers()
                    self.wfile.write(dados)
                else:
                    dados = f.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/mpeg")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(len(dados)))
                    self.end_headers()
                    self.wfile.write(dados)
        except Exception:
            try:
                self.send_error(404)
            except Exception:
                pass

    # ---------- GET ----------
    def do_GET(self):
        caminho = urlparse(self.path).path
        if caminho in ("/", "/index.html"):
            self._arquivo(os.path.join(WEB_DIR, "index.html"), TIPOS[".html"])
        elif caminho == "/api/videos":
            self._json({"videos": listar_videos()})
        elif caminho == "/api/temas":
            self._json({"temas": temas.listar_temas_com_busca()})
        elif caminho == "/api/templates":
            self._json({"templates": [{"id": i, "nome": n}
                                      for i, n in nucleo.TEMPLATES.items()]})
        elif caminho == "/api/audio/buscar":
            self._api_audio_buscar()
        elif caminho == "/api/tiktok/status":
            self._api_tiktok_status()
        elif caminho.startswith("/api/audio/preview/"):
            # ids do Openverse são UUIDs (strings), não inteiros.
            track_id = unquote(os.path.basename(caminho))
            if not track_id:
                self.send_error(404)
            else:
                self._api_audio_preview(track_id)
        elif caminho.startswith("/videos/"):
            nome = os.path.basename(caminho)
            self._arquivo(os.path.join(SAIDA_WEB, nome), TIPOS[".mp4"])
        else:
            alvo = os.path.join(WEB_DIR, caminho.lstrip("/"))
            ext = os.path.splitext(alvo)[1].lower()
            if os.path.isfile(alvo) and ext in TIPOS:
                self._arquivo(alvo, TIPOS[ext])
            else:
                self.send_error(404)

    def _api_audio_buscar(self):
        """GET /api/audio/buscar?tema=<nome> OU ?query=<texto>.

        Busca até 5 trilhas e já baixa cada uma pro temp dir (cache/preview).
        Soft-fail: retorna `opcoes: []` se a chave não estiver configurada.
        """
        try:
            params = dict(parse_qsl(urlparse(self.path).query))
            tema = (params.get("tema") or "").strip()
            query = (params.get("query") or "").strip()
            if tema:
                tema_obj = temas.obter_tema(tema)
                if tema_obj is None:
                    return self._json({"ok": False, "erro": "Tema não encontrado."}, 400)
                query = (tema_obj.get("musica_busca") or tema_obj.get("busca")
                         or "ambient hopeful inspirational background")
            if not query:
                return self._json(
                    {"ok": False, "erro": "Informe um tema ou uma busca."}, 400)
            opcoes = _buscar_audio(query, n=5)
            self._json({"ok": True, "opcoes": opcoes})
        except Exception as e:
            self._json({"ok": False, "erro": "Erro ao buscar áudio: %s" % e,
                        "opcoes": []}, 500)

    def _api_audio_preview(self, track_id):
        """GET /api/audio/preview/<track_id> -> serve o MP3 com Range."""
        caminho = audio_cache.get(track_id)
        if not caminho or not os.path.exists(caminho):
            # Download sob demanda (a URL veio do /api/audio/buscar).
            url = audio_url_map.get(track_id)
            caminho = _baixar_para_cache(track_id, url) if url else None
        if not caminho or not os.path.exists(caminho):
            self.send_error(404)
            return
        self._servir_mp3(caminho)

    def _api_tiktok_status(self):
        """GET /api/tiktok/status -> JSON snapshot of TikTok auth state.

        Cheap, no side effects. Safe to call on every page load. The response
        shape is documented in the publish-flow spec (issue #3):
        {configured: bool, expires_at: ISO or null, scope_ok: bool}.
        """
        try:
            self._json(tiktok_auth.tiktok_status())
        except Exception as e:
            self._json({"ok": False, "erro": "Erro ao checar TikTok: %s" % e}, 500)

    # ---------- POST ----------
    def do_POST(self):
        caminho = urlparse(self.path).path
        if caminho == "/api/gerar":
            self._gerar()
        elif caminho == "/api/preview":
            self._preview()
        elif caminho == "/api/preview_camadas":
            self._preview_camadas()
        elif caminho == "/api/preparar_auto":
            self._preparar_auto()
        elif caminho == "/api/buscar_fundos":
            self._buscar_fundos()
        elif caminho == "/api/gerar_frases":
            self._gerar_frases()
        elif caminho == "/api/gerar_legenda":
            self._gerar_legenda()
        else:
            self.send_error(404)

    def _gerar(self):
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))

            if not dados.get("imagem") and not dados.get("imagens"):
                return self._json({"ok": False, "erro": "Envie uma imagem de fundo."}, 400)
            frases = [l.strip() for l in (dados.get("textos") or "").splitlines() if l.strip()]
            if not frases:
                return self._json({"ok": False, "erro": "Escreva pelo menos uma frase."}, 400)

            from PIL import Image
            try:
                if dados.get("imagens"):
                    imagem = [io.BytesIO(decodificar_imagem(x)) for x in dados["imagens"]]
                    Image.open(io.BytesIO(decodificar_imagem(dados["imagens"][0]))).load()
                else:
                    imagem_bytes = decodificar_imagem(dados["imagem"])
                    imagem = io.BytesIO(imagem_bytes)
                    Image.open(io.BytesIO(imagem_bytes)).load()
            except Exception:
                return self._json({"ok": False, "erro": "Imagem inválida."}, 400)

            opcoes = {
                "duracao": _num(dados, "duracao", nucleo.DURACAO_PADRAO),
                "fade": _num(dados, "fade", nucleo.FADE_PADRAO),
                "fonte": (dados.get("fonte") or nucleo.FONTE_PADRAO),
                "cor": parse_cor(dados.get("cor")),
                "escurecer": int(_num(dados, "escurecer", nucleo.ESCURECER_PADRAO)),
                "tamanho": escala_de(dados),
                "template": resolve_template(dados, auto=True),
                "cor_destaque": resolve_cor_destaque(dados),
                "nome": "video_%d" % int(time.time() * 1000),
                "saida_dir": SAIDA_WEB,
                "volume_audio": _num(dados, "volume_audio", 0.5),
                "fade_in_audio": _num(dados, "fade_in_audio", 0.4),
                "fade_out_audio": _num(dados, "fade_out_audio", 0.8),
            }

            # Trilha de fundo opcional: `audio_id` escolhido no picker.
            # ids do Openverse são UUIDs (strings).
            audio_id = dados.get("audio_id")
            if audio_id is not None:
                audio_id = str(audio_id).strip() or None
            if audio_id is not None:
                busca_audio = (_busca_audio_do_payload(dados)
                               or "ambient hopeful inspirational background")
                try:
                    opcoes["audio_path"] = _resolver_audio_path(audio_id, busca_audio)
                except Exception:
                    opcoes["audio_path"] = None

            saida = nucleo.gerar_video(imagem, frases, opcoes)
            nome = os.path.basename(saida)
            self._json({"ok": True, "nome": nome, "url": "/videos/" + nome})
        except RuntimeError as e:
            self._json({"ok": False, "erro": str(e)}, 500)
        except Exception as e:
            self._json({"ok": False, "erro": "Erro ao gerar: %s" % e}, 500)

    def _preview(self):
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            if not dados.get("imagem"):
                return self._json({"ok": False, "erro": "Envie uma imagem."}, 400)
            linhas = [l.strip() for l in (dados.get("texto") or "").splitlines() if l.strip()]
            frase = linhas[0] if linhas else "Sua frase aqui"
            imagem_bytes = decodificar_imagem(dados["imagem"])
            opcoes = {
                "fonte": dados.get("fonte") or nucleo.FONTE_PADRAO,
                "cor": parse_cor(dados.get("cor")),
                "escurecer": int(_num(dados, "escurecer", nucleo.ESCURECER_PADRAO)),
                "tamanho": escala_de(dados),
                "template": resolve_template(dados, auto=False),
                "cor_destaque": resolve_cor_destaque(dados),
            }
            png = nucleo.render_frame_png(io.BytesIO(imagem_bytes), frase, opcoes)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)
        except Exception as e:
            self._json({"ok": False, "erro": "Erro no preview: %s" % e}, 500)

    def _preview_camadas(self):
        """Retorna o frame em DUAS camadas (bg + overlay) pra empilhar no cliente.

        Resposta JSON: {"bg": "<base64 png>", "overlay": "<base64 png>"} .
        O cliente anima só o bg e mantém o overlay estático por cima.
        """
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            if not dados.get("imagem"):
                return self._json({"ok": False, "erro": "Envie uma imagem."}, 400)
            linhas = [l.strip() for l in (dados.get("texto") or "").splitlines() if l.strip()]
            frase = linhas[0] if linhas else "Sua frase aqui"
            imagem_bytes = decodificar_imagem(dados["imagem"])
            opcoes = {
                "fonte": dados.get("fonte") or nucleo.FONTE_PADRAO,
                "cor": parse_cor(dados.get("cor")),
                "escurecer": int(_num(dados, "escurecer", nucleo.ESCURECER_PADRAO)),
                "tamanho": escala_de(dados),
                "template": resolve_template(dados, auto=False),
                "cor_destaque": resolve_cor_destaque(dados),
            }
            bg_png, ov_png = nucleo.render_layers_png(
                io.BytesIO(imagem_bytes), frase, opcoes)
            self._json({
                "ok": True,
                "bg": base64.b64encode(bg_png).decode("ascii"),
                "overlay": base64.b64encode(ov_png).decode("ascii"),
            })
        except Exception as e:
            self._json({"ok": False, "erro": "Erro no preview: %s" % e}, 500)

    def _preparar_auto(self):
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            tema = (dados.get("tema") or "").strip()
            if not tema:
                return self._json({"ok": False, "erro": "Digite um tema."}, 400)

            tema_obj = temas.obter_tema(tema)
            if tema_obj is None:
                return self._json({"ok": False, "erro": "Tema não encontrado. Disponíveis: %s" % ", ".join(temas.listar_temas())}, 400)

            busca = (dados.get("busca") or "").strip() or tema_obj["busca"]

            cta = (dados.get("cta") or "").strip() or temas.obter_cta(tema)

            frases = tema_obj["frases"]
            try:
                f = gemini.gerar_frases(tema, cta)
                if len(f) >= 5:
                    frases = f
            except Exception:
                pass

            try:
                imagens_bytes = pexels.buscar_fundos(busca, len(frases))
                if not imagens_bytes:
                    return self._json({"ok": False, "erro": "Nenhuma imagem de fundo encontrada para esse tema."}, 500)
            except Exception as e:
                return self._json({"ok": False, "erro": "Erro ao buscar fundos no Pexels: %s" % e}, 500)

            legenda = tema_obj["legenda"]
            try:
                legenda = gemini.gerar_legenda(tema, frases, cta)
            except Exception:
                pass

            # Música de fundo (soft-fail: sem chave/erro -> lista vazia).
            busca_audio = ((dados.get("musica_busca") or "").strip()
                           or tema_obj.get("musica_busca")
                           or tema_obj.get("busca")
                           or "ambient hopeful inspirational background")
            try:
                audio_opcoes = _buscar_audio(busca_audio, n=5)
            except Exception:
                audio_opcoes = []

            imagens_data = ["data:image/jpeg;base64," + base64.b64encode(b).decode() for b in imagens_bytes]
            self._json({
                "ok": True,
                "frases": frases,
                "legenda": legenda,
                "imagens": imagens_data,
                "cor": tema_obj["cor"],
                "template": nucleo.sortear_template(),
                "audio_opcoes": audio_opcoes,
            })
        except Exception as e:
            self._json({"ok": False, "erro": "Erro: %s" % e}, 500)

    def _buscar_fundos(self):
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            busca = (dados.get("busca") or "").strip()
            n = int(_num(dados, "n", 7))
            page = int(_num(dados, "page", 1))
            if not busca:
                tema = (dados.get("tema") or "").strip()
                tema_obj = temas.obter_tema(tema) if tema else None
                busca = tema_obj["busca"] if tema_obj else tema
            if not busca:
                return self._json({"ok": False, "erro": "Informe um tema ou uma busca de imagem."}, 400)
            imagens_bytes = pexels.buscar_fundos(busca, n, page=page)
            if not imagens_bytes:
                return self._json({"ok": False, "erro": "Nenhuma imagem encontrada."}, 500)
            imagens_data = ["data:image/jpeg;base64," + base64.b64encode(b).decode() for b in imagens_bytes]
            self._json({"ok": True, "imagens": imagens_data})
        except Exception as e:
            self._json({"ok": False, "erro": "Erro ao buscar: %s" % e}, 500)

    def _gerar_frases(self):
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            tema = (dados.get("tema") or "").strip()
            if not tema:
                return self._json({"ok": False, "erro": "Digite um tema."}, 400)
            frases = gemini.gerar_frases(tema, (dados.get("cta") or "").strip() or temas.obter_cta(tema))
            self._json({"ok": True, "frases": frases})
        except Exception as e:
            self._json({"ok": False, "erro": "Erro ao gerar frases: %s" % e}, 500)

    def _gerar_legenda(self):
        try:
            tamanho = int(self.headers.get("Content-Length", 0))
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            tema = (dados.get("tema") or "").strip()
            frases = dados.get("frases") or []
            if not tema:
                return self._json({"ok": False, "erro": "Digite um tema."}, 400)
            legenda = gemini.gerar_legenda(tema, frases, (dados.get("cta") or "").strip() or temas.obter_cta(tema))
            self._json({"ok": True, "legenda": legenda})
        except Exception as e:
            self._json({"ok": False, "erro": "Erro ao gerar legenda: %s" % e}, 500)


def main():
    porta = int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 8000
    os.makedirs(WEB_DIR, exist_ok=True)
    os.makedirs(SAIDA_WEB, exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    print("=" * 50)
    print("  Gerador de vídeos rodando!")
    print("  Abra no navegador:  http://localhost:%d" % porta)
    print("  (Ctrl+C para parar)")
    print("=" * 50)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")


if __name__ == "__main__":
    main()
