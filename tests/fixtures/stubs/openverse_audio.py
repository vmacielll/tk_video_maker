"""Stub for `openverse_audio` used by the SSE publish tests.

The publish flow without `--audio=auto` doesn't call openverse_audio. Provide
a stub so the server imports cleanly under PYTHONPATH override.
"""


def buscar_opcoes(query, n=5, chave=None):
    return []


def baixar_track(url, destino):
    raise RuntimeError("baixar_track not stubbed (no audio in this test)")
