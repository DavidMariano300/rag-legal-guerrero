"""Voz autoalojada: transcripción (Whisper) y síntesis (Piper), 100% open source y local.

Flags de la CLI de Piper y el nombre de la voz en español verificados manualmente contra el
paquete real 'piper-tts' antes de escribir este módulo (ver docs/spike_resultados.md).
"""

import io
import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException
from faster_whisper import WhisperModel

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "small")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "es")

PIPER_VOICE = os.environ.get("PIPER_VOICE", "es_MX-claude-high")
PIPER_MODELS_DIR = os.environ.get("PIPER_MODELS_DIR", "/app/models/piper")

_whisper_model: WhisperModel | None = None


def get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        _whisper_model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _whisper_model


def transcribe(audio_bytes: bytes) -> str:
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="No se recibió audio.")

    model = get_whisper_model()
    try:
        segments, _ = model.transcribe(io.BytesIO(audio_bytes), language=WHISPER_LANGUAGE)
    except Exception as exc:  # formato de audio no decodificable, archivo corrupto, etc.
        raise HTTPException(status_code=400, detail="No se pudo procesar el audio recibido.") from exc

    return " ".join(segment.text.strip() for segment in segments).strip()


def _voice_paths() -> tuple[Path, Path]:
    model_path = Path(PIPER_MODELS_DIR) / f"{PIPER_VOICE}.onnx"
    config_path = Path(PIPER_MODELS_DIR) / f"{PIPER_VOICE}.onnx.json"
    return model_path, config_path


def ensure_voice_downloaded() -> None:
    model_path, config_path = _voice_paths()
    if model_path.exists() and config_path.exists():
        return

    os.makedirs(PIPER_MODELS_DIR, exist_ok=True)
    try:
        subprocess.run(
            ["python", "-m", "piper.download_voices", PIPER_VOICE, "--download-dir", PIPER_MODELS_DIR],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"No se pudo descargar el modelo de voz '{PIPER_VOICE}'. Verifique conectividad "
                "o configure la variable de entorno PIPER_VOICE con una voz válida."
            ),
        ) from exc


def synthesize(text: str) -> bytes:
    if not text.strip():
        raise HTTPException(status_code=400, detail="No hay texto para convertir a voz.")

    ensure_voice_downloaded()
    model_path, config_path = _voice_paths()

    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        try:
            subprocess.run(
                ["piper", "-m", str(model_path), "-c", str(config_path), "-f", tmp.name],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
                timeout=60,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise HTTPException(
                status_code=503, detail="El servicio de síntesis de voz falló al generar el audio."
            ) from exc

        return Path(tmp.name).read_bytes()
