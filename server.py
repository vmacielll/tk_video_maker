#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Servidor web simples do gerador de vídeos.

Roda o frontend (pasta web/) e expõe a API:
    POST /api/gerar   -> gera um vídeo (JSON, imagem em base64)
    GET  /api/videos  -> lista os vídeos gerados
    GET  /videos/<n>  -> serve o arquivo .mp4

Uso:
    python3 server.py            (porta 8000)
    python3 server.py 8080       (porta customizada)
"""

import os
import io
import json
import time
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import nucleo
import pexels
import temas
import gemini

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
SAIDA_WEB = os.path.join(BASE_DIR, "saida_web")

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
            }
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

            imagens_data = ["data:image/jpeg;base64," + base64.b64encode(b).decode() for b in imagens_bytes]
            self._json({
                "ok": True,
                "frases": frases,
                "legenda": legenda,
                "imagens": imagens_data,
                "cor": tema_obj["cor"],
                "template": nucleo.sortear_template(),
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
