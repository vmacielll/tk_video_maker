"""Stub for `pexels` used by the SSE publish tests.

The manual publish flow doesn't call pexels. Provide a stub so the server
imports cleanly under PYTHONPATH override.
"""


def buscar_fundos(query, n, page=1, chave=None):
    return [b"FAKE-IMAGE"] * n


def buscar_fundo(query, chave=None):
    return b"FAKE-IMAGE"
