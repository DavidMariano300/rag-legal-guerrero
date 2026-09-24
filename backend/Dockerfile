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

COPY backend/app ./app
COPY fixtures ./fixtures

# Pre-descarga la voz de Piper en tiempo de build para que la primera consulta de voz
# de un usuario real no tenga que esperar la descarga (ver app/voice.py).
RUN python -m piper.download_voices ${PIPER_VOICE} --download-dir ${PIPER_MODELS_DIR}

RUN chown -R appuser:appuser /app /home/appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
