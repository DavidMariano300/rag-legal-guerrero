import { authFetch } from "./auth";

export interface Fragmento {
  texto: string;
  fuente: string;
  ley: string | null;
  area: string;
  score: number;
}

export interface PlantillaSugerida {
  id: string;
  nombre: string;
}

export interface TiemposMs {
  recuperacion: number;
  generacion: number;
  total: number;
}

export interface QueryResponse {
  respuesta: string;
  fragmentos: Fragmento[];
  disclaimer: string;
  plantilla_sugerida: PlantillaSugerida | null;
  tiempos_ms: TiemposMs;
}

export async function consultar(
  pregunta: string,
  area: string,
  sessionId: string,
  incluirDocumentos: boolean,
): Promise<QueryResponse> {
  const res = await authFetch("/api/query", {
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
    throw new Error(res.status === 401 ? "Tu sesión expiró, inicia sesión de nuevo." : `Error del servidor (${res.status})`);
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

  const res = await authFetch("/api/documents/upload", {
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
  const res = await authFetch(`/api/documents/${sessionId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error(`Error al borrar documentos (${res.status})`);
  }
}

export async function transcribirAudio(sessionId: string, audio: Blob): Promise<string> {
  const formData = new FormData();
  formData.append("audio", audio, "consulta.webm");
  formData.append("session_id", sessionId);

  const res = await authFetch("/api/voice/transcribir", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(detail?.detail || `Error al transcribir audio (${res.status})`);
  }

  const data = await res.json();
  return data.texto as string;
}

export async function hablarTexto(texto: string): Promise<Blob> {
  const res = await authFetch("/api/voice/hablar", {
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
  const res = await authFetch("/api/documents/templates");
  if (!res.ok) {
    throw new Error(`Error al listar plantillas (${res.status})`);
  }
  return res.json();
}

export async function generarDocumento(templateId: string, valores: Record<string, string>): Promise<Blob> {
  const res = await authFetch(`/api/documents/generate/${templateId}`, {
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
