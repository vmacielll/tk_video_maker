"""Stub for `gemini` used by the SSE publish tests.

The manual publish flow doesn't call gemini. Provide a stub so the server
imports cleanly under PYTHONPATH override.
"""


def gerar_frases(tema, cta=None, n=5):
    return [
        f"Frase 1 sobre {tema}",
        f"Frase 2 sobre {tema}",
        f"Frase 3 sobre {tema}",
        f"Frase 4 sobre {tema}",
        f"Frase 5 sobre {tema}",
    ]


def gerar_legenda(tema, frases, cta=None):
    return f"Legenda de teste para {tema}"
