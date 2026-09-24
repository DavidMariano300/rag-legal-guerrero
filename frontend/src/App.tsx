import { FormEvent, useState } from "react";
import { consultar, QueryResponse } from "./api";

const AREAS = [
  { value: "", label: "Todas las áreas" },
  { value: "Civil y Familiar", label: "Civil y Familiar" },
  { value: "Penal", label: "Penal" },
  { value: "Laboral", label: "Laboral" },
  { value: "Administrativo y Fiscal", label: "Administrativo y Fiscal" },
  { value: "Amparo", label: "Amparo" },
];

export default function App() {
  const [pregunta, setPregunta] = useState("");
  const [area, setArea] = useState("");
  const [resultado, setResultado] = useState<QueryResponse | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!pregunta.trim()) return;

    setCargando(true);
    setError(null);
    setResultado(null);

    try {
      const data = await consultar(pregunta.trim(), area);
      setResultado(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ocurrió un error inesperado.");
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="page">
      <header className="header">
        <h1>RAG Legal Guerrero</h1>
        <p className="subtitle">Consulta rápida de legislación estatal y federal aplicable en Guerrero</p>
      </header>

      <div className="ai-disclaimer">
        Este sistema utiliza inteligencia artificial y puede cometer errores u omisiones. Verifique siempre
        la información contra la fuente original antes de utilizarla en cualquier trámite o gestión legal.
      </div>

      <form className="query-panel" onSubmit={handleSubmit}>
        <label className="field">
          <span>Área del derecho</span>
          <select value={area} onChange={(e) => setArea(e.target.value)}>
            {AREAS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Tu pregunta</span>
          <textarea
            value={pregunta}
            onChange={(e) => setPregunta(e.target.value)}
            placeholder="Ej. ¿Cuál es el plazo para contestar una demanda civil?"
            rows={3}
          />
        </label>

        <button type="submit" disabled={cargando || !pregunta.trim()}>
          {cargando ? "Consultando..." : "Consultar"}
        </button>
      </form>

      {error && <div className="error-panel">{error}</div>}

      {resultado && (
        <div className="results">
          <section className="panel respuesta-panel">
            <h2>Respuesta</h2>
            <p>{resultado.respuesta}</p>
          </section>

          <section className="panel fragmentos-panel">
            <h2>Fragmentos citados (fuente original)</h2>
            {resultado.fragmentos.length === 0 && <p>No se encontraron fragmentos relevantes.</p>}
            {resultado.fragmentos.map((f, idx) => (
              <div className="fragmento" key={idx}>
                <div className="fragmento-fuente">
                  {f.fuente} · {f.area} · similitud {(f.score * 100).toFixed(0)}%
                </div>
                <p className="fragmento-texto">{f.texto}</p>
              </div>
            ))}
          </section>

          <div className="result-disclaimer">{resultado.disclaimer}</div>
        </div>
      )}
    </div>
  );
}
