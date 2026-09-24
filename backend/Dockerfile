FROM python:3.11-slim

WORKDIR /app

RUN groupadd -r appuser && useradd -r -m -d /home/appuser -g appuser appuser
ENV HF_HOME=/home/appuser/.cache/huggingface

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY fixtures ./fixtures

RUN chown -R appuser:appuser /app /home/appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
