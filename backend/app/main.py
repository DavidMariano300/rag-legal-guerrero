from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel

from app import documents, generation, voice
from app.rag import answer_query

app = FastAPI(title="RAG Legal Guerrero — Spike técnico")


class QueryRequest(BaseModel):
    pregunta: str
    area: str | None = None
    session_id: str | None = None
    incluir_documentos: bool = False


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/query")
def query(request: QueryRequest) -> dict:
    extra_fragments = []
    if request.incluir_documentos and request.session_id:
        extra_fragments = documents.retrieve_session_fragments(request.session_id, request.pregunta)

    return answer_query(request.pregunta, request.area, extra_fragments)


@app.post("/api/documents/upload")
async def upload_document(file: UploadFile = File(...), session_id: str = Form(...)) -> dict:
    return await documents.procesar_subida(session_id, file)


@app.delete("/api/documents/{session_id}")
def delete_documents(session_id: str) -> dict:
    documents.eliminar_documentos_sesion(session_id)
    return {"status": "ok"}


@app.get("/api/documents/templates")
def list_templates() -> list[dict]:
    return generation.list_templates()


@app.post("/api/documents/generate/{template_id}")
def generate_document(template_id: str, values: dict[str, str]) -> Response:
    content = generation.generate_document(template_id, values)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{template_id}.docx"'},
    )


@app.post("/api/voice/transcribir")
async def transcribir(audio: UploadFile = File(...), session_id: str = Form(...)) -> dict:
    audio_bytes = await audio.read()
    texto = voice.transcribe(audio_bytes)
    return {"texto": texto}


class HablarRequest(BaseModel):
    texto: str


@app.post("/api/voice/hablar")
def hablar(request: HablarRequest) -> Response:
    audio_bytes = voice.synthesize(request.texto)
    return Response(content=audio_bytes, media_type="audio/wav")
