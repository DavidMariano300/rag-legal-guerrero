"""Evaluación de punta a punta con el pipeline real (answer_query) sobre casos con respuesta conocida.

Mide lo que pide el producto (docs/investigacion_llm.md §7):
- recuperación: % de respuestas cuyo contexto trajo el artículo correcto (meta > 90 %);
- respuestas: la pre-calificación por `clave` es solo una ayuda; la exactitud (meta > 80 %) se califica
  a mano con el campo `esperada` de casos.json y el JSONL que deja esta corrida.

Uso (desde la raíz del repo, con el mismo entorno que el backend):
  PYTHONPATH=backend python -m eval.evaluar --corridas 3 --salida /tmp/eval.jsonl
"""

import argparse
import json
import re
import time
from pathlib import Path

from app.rag import EMBEDDING_MODEL_NAME, OLLAMA_MODEL, OLLAMA_NUM_CTX, _armar_prompt, answer_query



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corridas", type=int, default=1)
    parser.add_argument("--salida", required=True)
    # casos.json: los casos con que se ajustó el sistema. casos_validacion.json: preguntas que nunca se
    # usaron para ajustar; la cifra que se reporta es la de validación.
    parser.add_argument("--casos", default="casos.json")
    args = parser.parse_args()
    CASOS = json.loads((Path(__file__).parent / args.casos).read_text(encoding="utf-8"))

    filas = []
    for corrida in range(1, args.corridas + 1):
        for n, caso in enumerate(CASOS, start=1):
            t0 = time.time()
            r = answer_query(caso["pregunta"], caso["area"])
            filas.append({
                "llm": OLLAMA_MODEL, "num_ctx": OLLAMA_NUM_CTX, "embeddings": EMBEDDING_MODEL_NAME, "corrida": corrida, "caso": n,
                # fuente "^$": control negativo (el corpus no tiene la respuesta; lo correcto es rechazar).
                "llega": None if caso["fuente"] == "^$" else any(re.match(caso["fuente"], f["fuente"]) for f in r["fragmentos"]),
                # Con un contexto chico (OLLAMA_NUM_CTX) el modelo no lee todos los fragmentos encontrados.
                "llega_al_prompt": None if caso["fuente"] == "^$" else any(
                    re.match(caso["fuente"], f["fuente"]) and f"[Fuente: {f['fuente']}]" in prompt
                    for prompt in [_armar_prompt(caso["pregunta"], r["fragmentos"])] for f in r["fragmentos"]),
                "respaldada": r["respaldada"], "clave": bool(re.search(caso["clave"], r["respuesta"], re.I)),
                "segundos": round(time.time() - t0, 1), "respuesta": r["respuesta"],
                "fuentes": [f["fuente"][:90] for f in r["fragmentos"]],
            })
            f = filas[-1]
            print(f"c{corrida} #{n:02d} llega={f['llega']} resp={int(f['respaldada'])} clave={int(f['clave'])} {f['segundos']:5.1f}s", flush=True)

    with open(args.salida, "w", encoding="utf-8") as out:
        out.writelines(json.dumps(f, ensure_ascii=False) + "\n" for f in filas)
    for campo, nombre in (("llega", "Recuperación (la búsqueda encuentra el artículo)"),
                         ("llega_al_prompt", "Recuperación en el prompt (el modelo lee el artículo)"), ("respaldada", "Respaldadas"), ("clave", "Pre-calificación por clave")):
        medidas = [f[campo] for f in filas if f[campo] is not None]
        print(f"{nombre}: {sum(medidas)}/{len(medidas)} = {sum(medidas) / len(medidas):.0%}")
    fallas = sorted({f["caso"] for f in filas if f["llega"] is False})
    print("Casos sin el artículo correcto:", fallas or "ninguno")


if __name__ == "__main__":
    main()
