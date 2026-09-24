from fastapi import FastAPI
from pydantic import BaseModel

from app.rag import answer_query

app = FastAPI(title="RAG Legal Guerrero — Spike técnico")


class QueryRequest(BaseModel):
    pregunta: str
    area: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/query")
def query(request: QueryRequest) -> dict:
    return answer_query(request.pregunta, request.area)
