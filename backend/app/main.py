import logging
import os
import secrets
import threading
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app import documents, generation, voice
from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.db import Base, engine, get_db
from app.models import User
from app.rag import answer_query
from app.rate_limit import limiter

logger = logging.getLogger(__name__)


def _precalentar() -> None:
    """Una consulta completa al arrancar carga embeddings, BM25, índice de vigencia y el LLM: sin esto la
    primera consulta de un usuario tardaba 27 s en GPU (94 s en CPU) en vez de 3-5 s."""
    try:
        answer_query("¿Qué es una ley?")
        logger.warning("Precalentamiento listo.")  # warning: el nivel por defecto no muestra info
    except Exception:  # nunca tumba el arranque: la primera consulta solo será más lenta
        logger.exception("Falló el precalentamiento.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    documents.iniciar_limpieza_periodica()
    threading.Thread(target=_precalentar, daemon=True).start()
    yield


app = FastAPI(title="RAG Legal Guerrero — Spike técnico", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/api/auth/register", response_model=TokenResponse)
@limiter.limit("10/minute")
def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existente = db.query(User).filter(User.email == body.email).first()
    if existente is not None:
        raise HTTPException(status_code=409, detail="Ya existe una cuenta con ese correo.")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id))


@app.post("/api/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

    return TokenResponse(access_token=create_access_token(user.id))


# Acceso sin registro para la demo con abogados. Todos los invitados comparten un usuario; los documentos
# subidos se separan por session_id, no por usuario. Desactivado salvo que PERMITIR_INVITADOS=true.
PERMITIR_INVITADOS = os.environ.get("PERMITIR_INVITADOS", "false").lower() == "true"
EMAIL_INVITADO = "invitado@amate.invalid"  # .invalid no pasa EmailStr: nadie puede registrarlo ni entrar con él
HORAS_TOKEN_INVITADO = 4


@app.post("/api/auth/invitado", response_model=TokenResponse)
@limiter.limit("5/minute")
def entrar_como_invitado(request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    if not PERMITIR_INVITADOS:
        raise HTTPException(status_code=404, detail="El acceso como invitado está desactivado.")

    user = db.query(User).filter(User.email == EMAIL_INVITADO).first()
    if user is None:
        user = User(email=EMAIL_INVITADO, password_hash=hash_password(secrets.token_urlsafe(32)))
        db.add(user)
        db.commit()
        db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id, horas=HORAS_TOKEN_INVITADO))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Consulta legal (protegida)
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    pregunta: str
    area: str | None = None
    session_id: str | None = None
    incluir_documentos: bool = False


@app.post("/api/query")
@limiter.limit("20/minute")
def query(request: Request, body: QueryRequest, current_user: User = Depends(get_current_user)) -> dict:
    extra_fragments = []
    if body.incluir_documentos and body.session_id:
        extra_fragments = documents.retrieve_session_fragments(body.session_id, body.pregunta)

    try:
        resultado = answer_query(body.pregunta, body.area, extra_fragments)
    except httpx.HTTPError:
        # Ollama caído o saturado (en CPU, varias consultas simultáneas superan el timeout de 120 s).
        logger.exception("Falló la generación con Ollama.")
        raise HTTPException(status_code=503, detail="El servicio está ocupado. Intente de nuevo en un momento.")
    resultado["plantilla_sugerida"] = generation.sugerir_plantilla(body.pregunta, resultado["respuesta"])
    return resultado


@app.post("/api/documents/upload")
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    return await documents.procesar_subida(session_id, file)


@app.delete("/api/documents/{session_id}")
def delete_documents(session_id: str, current_user: User = Depends(get_current_user)) -> dict:
    documents.eliminar_documentos_sesion(session_id)
    return {"status": "ok"}


@app.get("/api/documents/templates")
def list_templates(current_user: User = Depends(get_current_user)) -> list[dict]:
    return generation.list_templates()


@app.post("/api/documents/generate/{template_id}")
def generate_document(
    template_id: str, values: dict[str, str], current_user: User = Depends(get_current_user)
) -> Response:
    content = generation.generate_document(template_id, values)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{template_id}.docx"'},
    )


@app.post("/api/voice/transcribir")
@limiter.limit("15/minute")
async def transcribir(
    request: Request,
    audio: UploadFile = File(...),
    session_id: str = Form(...),
    current_user: User = Depends(get_current_user),
) -> dict:
    audio_bytes = await audio.read()
    voice.validar_duracion_audio(audio_bytes)
    texto = voice.transcribe(audio_bytes)
    return {"texto": texto}


class HablarRequest(BaseModel):
    texto: str


@app.post("/api/voice/hablar")
@limiter.limit("15/minute")
def hablar(request: Request, body: HablarRequest, current_user: User = Depends(get_current_user)) -> Response:
    audio_bytes = voice.synthesize(body.texto)
    return Response(content=audio_bytes, media_type="audio/wav")
