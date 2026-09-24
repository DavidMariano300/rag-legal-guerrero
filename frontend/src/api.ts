export interface Fragmento {
  texto: string;
  fuente: string;
  area: string;
  score: number;
}

export interface QueryResponse {
  respuesta: string;
  fragmentos: Fragmento[];
  disclaimer: string;
}

export async function consultar(
  pregunta: string,
  area: string,
  sessionId: string,
  incluirDocumentos: boolean,
): Promise<QueryResponse> {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pregunta,
      area: area || null,
      session_id: sessionId,
      incluir_documentos: incluirDocumentos,
    }),
  });

  if (!res.ok) {
    throw new Error(`Error del servidor (${res.status})`);
  }

  return res.json();
}

export interface DocumentoSubido {
  filename: string;
  fragmentos_indexados: number;
}

export async function subirDocumento(sessionId: string, file: File): Promise<DocumentoSubido> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);

  const res = await fetch("/api/documents/upload", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Error al subir el documento (${res.status})`);
  }

  return res.json();
}

export async function borrarDocumentosSesion(sessionId: string): Promise<void> {
  const res = await fetch(`/api/documents/${sessionId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`Error al borrar documentos (${res.status})`);
  }
}

export async function transcribirAudio(sessionId: string, audio: Blob): Promise<string> {
  const formData = new FormData();
  formData.append("audio", audio, "consulta.webm");
  formData.append("session_id", sessionId);

  const res = await fetch("/api/voice/transcribir", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error(`Error al transcribir audio (${res.status})`);
  }

  const data = await res.json();
  return data.texto as string;
}

export async function hablarTexto(texto: string): Promise<Blob> {
  const res = await fetch("/api/voice/hablar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ texto }),
  });

  if (!res.ok) {
    throw new Error(`Error al generar audio (${res.status})`);
  }

  return res.blob();
}

export interface CampoPlantilla {
  nombre: string;
  etiqueta: string;
  tipo: "texto" | "numero" | "fecha";
  requerido: boolean;
}

export interface Plantilla {
  id: string;
  nombre: string;
  descripcion: string;
  campos: CampoPlantilla[];
}

export async function listarPlantillas(): Promise<Plantilla[]> {
  const res = await fetch("/api/documents/templates");
  if (!res.ok) {
    throw new Error(`Error al listar plantillas (${res.status})`);
  }
  return res.json();
}

export async function generarDocumento(templateId: string, valores: Record<string, string>): Promise<Blob> {
  const res = await fetch(`/api/documents/generate/${templateId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(valores),
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Error al generar el documento (${res.status})`);
  }

  return res.blob();
}
