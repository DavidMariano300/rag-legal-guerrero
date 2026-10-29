FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -r appuser && useradd -r -m -d /home/appuser -g appuser appuser
ENV HF_HOME=/home/appuser/.cache/huggingface
ENV PIPER_MODELS_DIR=/app/models/piper
ENV PIPER_VOICE=es_MX-claude-high

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modelos antes del COPY del código: así un cambio de código no vuelve a descargar ~2.8 GB. Se descargan
# ya como appuser: un chown -R posterior duplicaría esos ~2.8 GB en otra capa de la imagen.
USER appuser
# Hornea el modelo de embeddings en la imagen: en tiempo de ejecución HF_HUB_OFFLINE=1 (docker-compose.yml).
# Solo pesos y tokenizador: el repo de bge-m3 trae además ONNX y ColBERT que no se usan (varios GB).
ARG EMBEDDING_MODEL=BAAI/bge-m3
RUN python -c "from huggingface_hub import snapshot_download; snapshot_download('${EMBEDDING_MODEL}', allow_patterns=['*.json', '*.safetensors', 'pytorch_model.bin', 'sentencepiece.bpe.model', '1_Pooling/*', '*.txt'], ignore_patterns=['onnx/*'])"

# Whisper también se hornea: faster-whisper lo descargaba de Hugging Face en la primera consulta de voz.
ARG WHISPER_MODEL_SIZE=small
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL_SIZE}', device='cpu', compute_type='int8')"
USER root

COPY backend/app ./app
COPY backend/tests ./tests
COPY backend/pytest.ini .
COPY fixtures ./fixtures

# Pre-descarga la voz de Piper en tiempo de build para que la primera consulta de voz
# de un usuario real no tenga que esperar la descarga (ver app/voice.py).
RUN python -m piper.download_voices ${PIPER_VOICE} --download-dir ${PIPER_MODELS_DIR}

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
