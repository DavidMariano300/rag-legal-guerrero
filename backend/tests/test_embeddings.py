import numpy as np

import app.rag as rag


class EmbedderFalso:
    def encode(self, entrada, **_):
        self.recibido = entrada
        return np.zeros((len(entrada), 3)) if isinstance(entrada, list) else np.zeros(3)


def test_e5_lleva_prefijos_y_bge_m3_no(monkeypatch):
    falso = EmbedderFalso()
    monkeypatch.setattr(rag, "get_embedder", lambda: falso)

    monkeypatch.setattr(rag, "EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-small")
    rag.embed_query("¿plazo para demandar?")
    assert falso.recibido == "query: ¿plazo para demandar?"
    rag.embed_passages(["Prescriben en dos meses..."])
    assert falso.recibido == ["passage: Prescriben en dos meses..."]

    # bge-m3 se entrenó sin prefijos: ponérselos degradaría los vectores.
    monkeypatch.setattr(rag, "EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    rag.embed_query("¿plazo para demandar?")
    assert falso.recibido == "¿plazo para demandar?"
