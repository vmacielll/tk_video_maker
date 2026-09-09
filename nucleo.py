#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Núcleo do gerador de vídeos 9:16 (TikTok/UGC).

Função principal: gerar_video(imagem, frases, opcoes) -> caminho do .mp4
"""

import io
import os
import random
import re
import tempfile
import subprocess

from PIL import Image, ImageDraw, ImageFont

# ---------------- Dimensões e padrões ----------------
CANVAS_W = 1080
CANVAS_H = 1920
MARGEM_X = 120
MARGEM_Y = 280
FPS = 30

DURACAO_PADRAO = 2.5
FADE_PADRAO = 0.4
COR_PADRAO = (255, 255, 255)
COR_SOMBRA = (0, 0, 0, 150)
ESCURECER_PADRAO = 70

FONTES = {
    "arial bold": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "arial": "/System/Library/Fonts/Supplemental/Arial.ttf",
    "georgia bold": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    "georgia": "/System/Library/Fonts/Supplemental/Georgia.ttf",
    "helvetica": "/System/Library/Fonts/Helvetica.ttc",
    "times": "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "futura": "/System/Library/Fonts/Supplemental/Futura.ttc",
}
FONTE_PADRAO = "georgia bold"

# ---------------- Templates de texto ----------------
# Registro dos 6 templates visuais. ID estável -> nome de exibição.
TEMPLATES = {
    "inferior": "Inferior",
    "cartao": "Cartão",
    "destaque": "Palavra em destaque",
    "topo_base": "Topo + base",
    "lista": "Lista numerada",
    "moldura": "Moldura",
}
TEMPLATE_PADRAO = "inferior"
COR_DESTAQUE_PADRAO = (212, 175, 55)
ZOOM_MAX = 1.10  # zoom máximo do efeito Ken Burns (zoom-in lento do fundo)


def sortear_template():
    """Retorna um id de template aleatório (rotação automática)."""
    return random.choice(list(TEMPLATES.keys()))

# Remove emojis (não renderizam bem em texto), mantém acentos e setas (->).
EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F1E0-\U0001F1FF"
    "]+", flags=re.UNICODE
)


def resolver_fonte(nome):
    if nome and os.path.exists(nome):
        return nome
    return FONTES.get((nome or "").lower(), FONTES[FONTE_PADRAO])


def tirar_emoji(texto):
    return EMOJI_RE.sub("", texto).strip()


def quebrar_linhas(draw, texto, fonte, max_w):
    palavras = texto.split()
    linhas = []
    atual = ""
    for p in palavras:
        teste = (atual + " " + p).strip()
        bbox = draw.textbbox((0, 0), teste, font=fonte)
        if bbox[2] - bbox[0] <= max_w:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def ajustar_fonte(draw, texto, caminho_fonte, max_w, max_h, escala=1.0):
    # acha o maior tamanho que cabe na área
    base = 120
    while base > 24:
        fonte = ImageFont.truetype(caminho_fonte, base)
        linhas = quebrar_linhas(draw, texto, fonte, max_w)
        ref = draw.textbbox((0, 0), "Ag", font=fonte)
        altura_linha = ref[3] - ref[1]
        espacamento = int(altura_linha * 0.25)
        altura_total = len(linhas) * altura_linha + (len(linhas) - 1) * espacamento
        if altura_total <= max_h:
            break
        base -= 6
    # aplica a escala do usuário (ex.: 0.8 = 80%)
    tamanho = max(int(base * escala), 12)
    fonte = ImageFont.truetype(caminho_fonte, tamanho)
    linhas = quebrar_linhas(draw, texto, fonte, max_w)
    ref = draw.textbbox((0, 0), "Ag", font=fonte)
    altura_linha = ref[3] - ref[1]
    espacamento = int(altura_linha * 0.25)
    altura_total = len(linhas) * altura_linha + (len(linhas) - 1) * espacamento
    return fonte, linhas, altura_linha, espacamento, altura_total


def cobrir(img, w, h):
    iw, ih = img.size
    escala = max(w / iw, h / ih)
    nw, nh = int(iw * escala), int(ih * escala)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def cobrir_zoom(img, w, h, zoom=1.0):
    """Igual a `cobrir`, mas aplica um fator de zoom (mantém crop central).

    Com zoom>1 a imagem fica maior que a tela; o centro é preservado,
    criando o efeito de aproximação lenta (Ken Burns).
    """
    iw, ih = img.size
    escala = max(w / iw, h / ih) * zoom
    nw, nh = max(int(iw * escala), w), max(int(ih * escala), h)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))


def escurecer_imagem(img, nivel):
    if nivel <= 0:
        return img
    overlay = Image.new("RGBA", img.size, (0, 0, 0, int(nivel)))
    return Image.alpha_composite(img, overlay)


def _desenhar_centralizado(d, linhas, fonte, altura_linha, espacamento, cor_rgba, y):
    """Desenha linhas de texto centralizadas horizontalmente com sombra."""
    for linha in linhas:
        bbox = d.textbbox((0, 0), linha, font=fonte)
        largura = bbox[2] - bbox[0]
        x = (CANVAS_W - largura) / 2
        d.text((x + 4, y + 5), linha, font=fonte, fill=COR_SOMBRA)
        d.text((x, y), linha, font=fonte, fill=cor_rgba)
        y += altura_linha + espacamento


def _overlay_inferior(d, overlay, texto, caminho_fonte, cor_rgba, escala):
    """Template 'inferior': texto ancorado embaixo + scrim vertical escuro."""
    # Scrim escuro com gradiente vertical cobrindo o terço inferior.
    topo = int(CANVAS_H * 2 / 3)
    altura = CANVAS_H - topo
    for i in range(altura):
        alpha = int(190 * (i / max(altura - 1, 1)))
        d.line([(0, topo + i), (CANVAS_W, topo + i)], fill=(0, 0, 0, alpha))
    # Texto branco com sombra na faixa inferior útil.
    max_w = CANVAS_W - 2 * MARGEM_X
    band_top = int(CANVAS_H * 0.68)
    band_h = int(CANVAS_H * 0.9) - band_top
    fonte, linhas, altura_linha, espacamento, altura_total = ajustar_fonte(
        d, texto, caminho_fonte, max_w, band_h, escala)
    y = band_top + (band_h - altura_total) / 2
    _desenhar_centralizado(d, linhas, fonte, altura_linha, espacamento, cor_rgba, y)


def _overlay_cartao(d, overlay, texto, caminho_fonte, cor_rgba, escala):
    """Template 'cartao': placa arredondada translúcida com texto dentro."""
    card_w = int(CANVAS_W * 0.8)
    pad = 60
    max_w = card_w - 2 * pad
    max_h = int(CANVAS_H * 0.6)
    fonte, linhas, altura_linha, espacamento, altura_total = ajustar_fonte(
        d, texto, caminho_fonte, max_w, max_h, escala)
    card_h = altura_total + 2 * pad
    x0 = (CANVAS_W - card_w) // 2
    y0 = (CANVAS_H - card_h) // 2
    d.rounded_rectangle([x0, y0, x0 + card_w, y0 + card_h], radius=40,
                        fill=(0, 0, 0, 140))
    _desenhar_centralizado(d, linhas, fonte, altura_linha, espacamento, cor_rgba,
                           y0 + pad)


def _overlay_destaque(d, overlay, texto, caminho_fonte, cor_rgba,
                      cor_destaque_rgba, escala):
    """Template 'destaque': primeira palavra grande em cor de destaque."""
    palavras = texto.split()
    palavra = palavras[0] if palavras else ""
    resto = " ".join(palavras[1:])
    max_w = CANVAS_W - 2 * MARGEM_X
    max_h_g = int(CANVAS_H * 0.32)
    max_h_r = int(CANVAS_H * 0.3)
    fonte_g, linhas_g, al_g, esp_g, altura_g = ajustar_fonte(
        d, palavra, caminho_fonte, max_w, max_h_g, escala * 1.5)
    gap = int(CANVAS_H * 0.04)
    if resto:
        fonte_r, linhas_r, al_r, esp_r, altura_r = ajustar_fonte(
            d, resto, caminho_fonte, max_w, max_h_r, escala * 0.85)
        y = (CANVAS_H - (altura_g + gap + altura_r)) / 2
        _desenhar_centralizado(d, linhas_g, fonte_g, al_g, esp_g, cor_destaque_rgba, y)
        _desenhar_centralizado(d, linhas_r, fonte_r, al_r, esp_r, cor_rgba,
                               y + altura_g + gap)
    else:
        y = (CANVAS_H - altura_g) / 2
        _desenhar_centralizado(d, linhas_g, fonte_g, al_g, esp_g, cor_destaque_rgba, y)

def _overlay_topo_base(d, overlay, texto, caminho_fonte, cor_rgba,
                       cor_destaque_rgba, escala):
    """Template 'topo_base': texto ancorado em cima + barra de destaque abaixo."""
    max_w = CANVAS_W - 2 * MARGEM_X
    band_top = int(CANVAS_H * 0.12)
    band_h = int(CANVAS_H * 0.45) - band_top
    fonte, linhas, altura_linha, espacamento, altura_total = ajustar_fonte(
        d, texto, caminho_fonte, max_w, band_h, escala)
    y = band_top + (band_h - altura_total) / 2
    _desenhar_centralizado(d, linhas, fonte, altura_linha, espacamento, cor_rgba, y)
    # Barra/régua horizontal fina na cor de destaque, abaixo do bloco de texto.
    bar_y = y + altura_total + int(CANVAS_H * 0.03)
    bar_w = int(CANVAS_W * 0.5)
    bar_x = (CANVAS_W - bar_w) // 2
    d.rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + 6], fill=cor_destaque_rgba)


def _overlay_lista(d, overlay, texto, caminho_fonte, cor_rgba,
                   cor_destaque_rgba, escala, indice, total):
    """Template 'lista': frases numeradas; as 2 últimas são CTA/'seguir'."""
    if total is not None and indice >= total - 2:
        # CTA (penúltima) em destaque centralizado; "seguir" (última) em branco.
        texto_cor = cor_destaque_rgba if indice == total - 2 else cor_rgba
        max_w = CANVAS_W - 2 * MARGEM_X
        max_h = int(CANVAS_H * 0.4)
        fonte, linhas, altura_linha, espacamento, altura_total = ajustar_fonte(
            d, texto, caminho_fonte, max_w, max_h, escala)
        y = (CANVAS_H - altura_total) / 2
        _desenhar_centralizado(d, linhas, fonte, altura_linha, espacamento,
                               texto_cor, y)
        return

    # Conteúdo: numera a partir de 1 (não duplica se já começar com número).
    rotulo = None
    corpo = texto
    if not (texto and texto[0].isdigit()):
        rotulo = "%d." % (indice + 1)
        corpo = texto

    max_w_txt = CANVAS_W - 2 * MARGEM_X - 220
    max_h = int(CANVAS_H * 0.5)
    fonte, linhas, altura_linha, espacamento, altura_total = ajustar_fonte(
        d, corpo, caminho_fonte, max_w_txt, max_h, escala)
    larg_txt = max(d.textbbox((0, 0), l, font=fonte)[2] -
                   d.textbbox((0, 0), l, font=fonte)[0] for l in linhas)
    y = (CANVAS_H - altura_total) / 2

    if rotulo:
        # Número grande e em destaque à esquerda do bloco de texto.
        fonte_num = ImageFont.truetype(caminho_fonte, int(fonte.size * 1.5))
        bbox_num = d.textbbox((0, 0), rotulo, font=fonte_num)
        larg_num = bbox_num[2] - bbox_num[0]
        num_h = bbox_num[3] - bbox_num[1]
        gap = int(CANVAS_W * 0.03)
        total_larg = larg_num + gap + larg_txt
        x_txt = (CANVAS_W - total_larg) / 2 + larg_num + gap
        y_num = y + (altura_total - num_h) / 2
        d.text((x_txt - gap - larg_num + 4, y_num + 5), rotulo, font=fonte_num,
               fill=COR_SOMBRA)
        d.text((x_txt - gap - larg_num, y_num), rotulo, font=fonte_num,
               fill=cor_destaque_rgba)
    else:
        x_txt = (CANVAS_W - larg_txt) / 2

    for linha in linhas:
        bbox = d.textbbox((0, 0), linha, font=fonte)
        larg = bbox[2] - bbox[0]
        x = x_txt + (larg_txt - larg)
        d.text((x + 4, y + 5), linha, font=fonte, fill=COR_SOMBRA)
        d.text((x, y), linha, font=fonte, fill=cor_rgba)
        y += altura_linha + espacamento


def _overlay_moldura(d, overlay, texto, caminho_fonte, cor_rgba,
                     cor_destaque_rgba, escala):
    """Template 'moldura': borda fina na cor de destaque + texto centralizado."""
    m = 60
    d.rounded_rectangle([m, m, CANVAS_W - m, CANVAS_H - m], radius=24,
                        outline=cor_destaque_rgba, width=8)
    max_w = CANVAS_W - 2 * MARGEM_X
    max_h = CANVAS_H - 2 * MARGEM_Y
    fonte, linhas, altura_linha, espacamento, altura_total = ajustar_fonte(
        d, texto, caminho_fonte, max_w, max_h, escala)
    y = (CANVAS_H - altura_total) / 2
    _desenhar_centralizado(d, linhas, fonte, altura_linha, espacamento, cor_rgba, y)


def _overlay_texto(texto, caminho_fonte, cor, escala, template,
                   cor_destaque, indice, total):
    """Constrói o overlay (fundo transparente) com texto + decoração do template."""
    texto = tirar_emoji(texto.strip())
    if template not in TEMPLATES:
        template = TEMPLATE_PADRAO
    overlay = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    cor_rgba = tuple(int(c) for c in cor) + (255,)
    destaque_rgba = tuple(int(c) for c in cor_destaque) + (255,)
    if template == "cartao":
        _overlay_cartao(d, overlay, texto, caminho_fonte, cor_rgba, escala)
    elif template == "destaque":
        _overlay_destaque(d, overlay, texto, caminho_fonte, cor_rgba,
                          destaque_rgba, escala)
    elif template == "topo_base":
        _overlay_topo_base(d, overlay, texto, caminho_fonte, cor_rgba,
                           destaque_rgba, escala)
    elif template == "lista":
        _overlay_lista(d, overlay, texto, caminho_fonte, cor_rgba,
                       destaque_rgba, escala, indice, total)
    elif template == "moldura":
        _overlay_moldura(d, overlay, texto, caminho_fonte, cor_rgba,
                         destaque_rgba, escala)
    else:  # inferior (padrão)
        _overlay_inferior(d, overlay, texto, caminho_fonte, cor_rgba, escala)
    return overlay


def renderizar_tela(bg, texto, caminho_fonte, cor, escala=1.0,
                    template=TEMPLATE_PADRAO, cor_destaque=COR_DESTAQUE_PADRAO,
                    indice=0, total=None):
    """Compoõe o fundo (bg RGBA) com o texto conforme o template escolhido."""
    overlay = _overlay_texto(texto, caminho_fonte, cor, escala, template,
                             cor_destaque, indice, total)
    return Image.alpha_composite(bg, overlay)


def _achar_ffmpeg():
    for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if os.path.exists(p):
            return p
    return "ffmpeg"


def montar_video(frames, saida, duracao, fade):
    """Monta o .mp4 a partir de sequências de frames (Ken Burns).

    frames: lista de DIRETÓRIOS; cada um contém f_%04d.png (uma sequência
    por frase). Aplica xfade de transição entre as sequências.
    """
    n = len(frames)
    cmd = [_achar_ffmpeg(), "-y"]
    for dir in frames:
        cmd += ["-framerate", str(FPS), "-i", os.path.join(dir, "f_%04d.png")]
    if n == 1:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-r", str(FPS), saida]
    else:
        filtros = []
        prev = "0:v"
        for i in range(1, n):
            offset = i * (duracao - fade)
            out = "v%d" % i
            filtros.append(
                "[%s][%d:v]xfade=transition=fade:duration=%.3f:offset=%.3f[%s]"
                % (prev, i, fade, offset, out))
            prev = out
        fc = ";".join(filtros)
        cmd += ["-filter_complex", fc, "-map", "[%s]" % prev,
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", "-r", str(FPS), saida]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg falhou:\n" + r.stderr[-1500:])


def gerar_video(imagem, frases, opcoes=None):
    """Gera um vídeo 9:16 a partir de uma imagem e uma lista de frases.

    imagem: caminho do arquivo OU objeto file-like (ex.: BytesIO)
    frases: lista de strings (uma por tela)
    opcoes: dict opcional com chaves:
        duracao (float), fade (float), fonte (str),
        cor (tupla r,g,b), escurecer (int 0-255),
        tamanho (float, escala da fonte), template (str),
        cor_destaque (tupla r,g,b),
        nome (str, sem extensão), saida_dir (str)
    Retorna o caminho completo do .mp4 gerado.
    """
    opcoes = opcoes or {}
    duracao = float(opcoes.get("duracao", DURACAO_PADRAO))
    fade = float(opcoes.get("fade", FADE_PADRAO))
    fonte_nome = opcoes.get("fonte", FONTE_PADRAO)
    cor = tuple(opcoes.get("cor", COR_PADRAO))
    escurecer = int(opcoes.get("escurecer", ESCURECER_PADRAO))
    escala = float(opcoes.get("tamanho", 1.0))
    template = opcoes.get("template") or TEMPLATE_PADRAO
    cor_destaque = tuple(opcoes.get("cor_destaque", COR_DESTAQUE_PADRAO))
    nome = opcoes.get("nome", "video")
    saida_dir = opcoes.get("saida_dir", tempfile.mkdtemp(prefix="saida_"))

    caminho_fonte = resolver_fonte(fonte_nome)
    if not os.path.exists(caminho_fonte):
        raise ValueError("Fonte não encontrada: %s" % fonte_nome)

    imagens = imagem if isinstance(imagem, (list, tuple)) else [imagem]

    frases_validas = []
    for frase in frases:
        frase = tirar_emoji(frase.strip())
        if frase:
            frases_validas.append(frase)
    if not frases_validas:
        raise ValueError("Nenhuma frase válida.")

    tmp = tempfile.mkdtemp(prefix="frames_")
    dirs = []
    total = len(frases_validas)
    n_frames = max(int(round(duracao * FPS)), 1)
    total_frames = max(n_frames * total, 1)
    for i, frase in enumerate(frases_validas):
        img = imagens[i % len(imagens)]
        origem = Image.open(img).convert("RGBA")
        # Layout/texto estático da frase (não sofre zoom).
        overlay = _overlay_texto(frase, caminho_fonte, cor, escala, template,
                                 cor_destaque, i, total)
        dirp = os.path.join(tmp, "frase_%d" % i)
        os.makedirs(dirp, exist_ok=True)
        # Ken Burns: zoom contínuo acumulado ao longo do vídeo inteiro
        # (sem reset entre frases — o xfade do montar_video suaviza a transição).
        for j in range(n_frames):
            frame_global = i * n_frames + j
            z = 1.0 + (ZOOM_MAX - 1.0) * (frame_global / max(total_frames - 1, 1))
            fundo = cobrir_zoom(origem, CANVAS_W, CANVAS_H, z)
            fundo = escurecer_imagem(fundo, escurecer)
            tela = Image.alpha_composite(fundo, overlay)
            tela.convert("RGB").save(os.path.join(dirp, "f_%04d.png" % j))
        dirs.append(dirp)

    os.makedirs(saida_dir, exist_ok=True)
    saida = os.path.join(saida_dir, nome + ".mp4")
    montar_video(dirs, saida, duracao, fade)
    return saida


def render_frame_png(imagem, frase, opcoes):
    """Renderiza um único frame (fundo + frase) e retorna os bytes PNG."""
    fonte_nome = opcoes.get("fonte", FONTE_PADRAO)
    cor = tuple(opcoes.get("cor", COR_PADRAO))
    escurecer = int(opcoes.get("escurecer", ESCURECER_PADRAO))
    escala = float(opcoes.get("tamanho", 1.0))
    template = opcoes.get("template") or TEMPLATE_PADRAO
    cor_destaque = tuple(opcoes.get("cor_destaque", COR_DESTAQUE_PADRAO))
    caminho_fonte = resolver_fonte(fonte_nome)
    fundo = Image.open(imagem).convert("RGBA")
    fundo = cobrir_zoom(fundo, CANVAS_W, CANVAS_H, 1.0)
    fundo = escurecer_imagem(fundo, escurecer)
    tela = renderizar_tela(fundo, tirar_emoji(frase.strip()), caminho_fonte, cor,
                           escala, template=template, cor_destaque=cor_destaque)
    buf = io.BytesIO()
    tela.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def render_layers_png(imagem, frase, opcoes):
    """Renderiza o frame em DUAS camadas separadas: (bg, overlay).

    bg: imagem RGB (já com escurecimento aplicado, sem texto).
    overlay: imagem RGBA transparente com texto + decoração do template.
    Servem pra empilhar no cliente (CSS) — o bg pode animar (Ken Burns)
    enquanto o overlay fica estático por cima.
    """
    fonte_nome = opcoes.get("fonte", FONTE_PADRAO)
    cor = tuple(opcoes.get("cor", COR_PADRAO))
    escurecer = int(opcoes.get("escurecer", ESCURECER_PADRAO))
    escala = float(opcoes.get("tamanho", 1.0))
    template = opcoes.get("template") or TEMPLATE_PADRAO
    cor_destaque = tuple(opcoes.get("cor_destaque", COR_DESTAQUE_PADRAO))
    caminho_fonte = resolver_fonte(fonte_nome)
    fundo = Image.open(imagem).convert("RGBA")
    fundo = cobrir_zoom(fundo, CANVAS_W, CANVAS_H, 1.0)
    fundo = escurecer_imagem(fundo, escurecer)
    overlay = _overlay_texto(tirar_emoji(frase.strip()), caminho_fonte, cor, escala,
                             template, cor_destaque, 0, 1)
    bg_buf = io.BytesIO()
    fundo.convert("RGB").save(bg_buf, "PNG")
    ov_buf = io.BytesIO()
    overlay.save(ov_buf, "PNG")
    return bg_buf.getvalue(), ov_buf.getvalue()
