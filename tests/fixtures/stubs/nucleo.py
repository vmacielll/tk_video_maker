"""Stub for `nucleo` used by the SSE publish tests.

Avoids running real ffmpeg (30s+) by returning a fake .mp4 file path.
Provides the constants server.py reads (`DURACAO_PADRAO`, etc.).
"""

CANVAS_H = 1920
CANVAS_W = 1080
COR_DESTAQUE_PADRAO = (255, 255, 255)
COR_PADRAO = (255, 255, 255)
COR_SOMBRA = (0, 0, 0)
DURACAO_PADRAO = 5.0
EMOJI_RE = None
ESCURECER_PADRAO = 0
FADE_PADRAO = 0.5
FONTES = {}
FONTE_PADRAO = "fake-font"
TEMPLATE_PADRAO = 0
TEMPLATES = {0: "default"}


def gerar_video(frames, frases, opcoes):
    """Return a path to a fake .mp4 file. No ffmpeg run."""
    import os
    out_dir = opcoes.get("saida_dir", "/tmp")
    os.makedirs(out_dir, exist_ok=True)
    name = opcoes.get("nome", "video_stub")
    out_path = os.path.join(out_dir, f"{name}.mp4")
    with open(out_path, "wb") as f:
        f.write(b"FAKE-MP4-FROM-STUB")
    return out_path


def sortear_template():
    return TEMPLATE_PADRAO


def render_frame_png(*args, **kwargs):
    raise NotImplementedError("render_frame_png not stubbed")


def render_layers_png(*args, **kwargs):
    raise NotImplementedError("render_layers_png not stubbed")
