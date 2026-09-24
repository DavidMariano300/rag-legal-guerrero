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

export async function consultar(pregunta: string, area: string): Promise<QueryResponse> {
  const res = await fetch("/api/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pregunta, area: area || null }),
  });

  if (!res.ok) {
    throw new Error(`Error del servidor (${res.status})`);
  }

  return res.json();
}
