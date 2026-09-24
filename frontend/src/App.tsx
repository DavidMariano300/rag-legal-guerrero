import { FormEvent, useState } from "react";
import { consultar, QueryResponse } from "./api";
import { useSettings } from "./hooks/useSettings";
import SettingsPanel from "./components/SettingsPanel";
import CopyButton from "./components/CopyButton";
import DocumentUpload from "./components/DocumentUpload";
import VoiceControls from "./components/VoiceControls";
import DocumentGenerator from "./components/DocumentGenerator";
import { getSessionId } from "./session";

const AREAS = [
  { value: "", label: "Todas las áreas" },
  { value: "Civil y Familiar", label: "Civil y Familiar" },
  { value: "Penal", label: "Penal" },
  { value: "Laboral", label: "Laboral" },
  { value: "Administrativo y Fiscal", label: "Administrativo y Fiscal" },
  { value: "Amparo", label: "Amparo" },
];

export default function App() {
  const { theme, setTheme, fontSize, setFontSize } = useSettings();
  const sessionId = getSessionId();

  const [pregunta, setPregunta] = useState("");
  const [area, setArea] = useState("");
  const [hasDocuments, setHasDocuments] = useState(false);
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
      const data = await consultar(pregunta.trim(), area, sessionId, hasDocuments);
      setResultado(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ocurrió un error inesperado.");
    } finally {
      setCargando(false);
    }
  }

  return (
    <div className="page">
      <div className="top-bar">
        <SettingsPanel theme={theme} setTheme={setTheme} fontSize={fontSize} setFontSize={setFontSize} />
      </div>

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

        <div className="composer">
          <textarea
            value={pregunta}
            onChange={(e) => setPregunta(e.target.value)}
            placeholder="Ej. ¿Cuál es el plazo para contestar una demanda civil?"
            rows={3}
          />

          <div className="composer-toolbar">
            <div className="composer-toolbar-left">
              <DocumentUpload sessionId={sessionId} onHasDocuments={setHasDocuments} />
              <VoiceControls onTranscribed={(texto) => setPregunta((prev) => (prev ? `${prev} ${texto}` : texto))} />
            </div>
            <button type="submit" className="primary-button" disabled={cargando || !pregunta.trim()}>
              {cargando ? "Consultando..." : "Consultar"}
            </button>
          </div>
        </div>
      </form>

      {error && <div className="error-panel">{error}</div>}

      {resultado && (
        <div className="results">
          <section className="panel respuesta-panel">
            <div className="panel-header">
              <h2>Respuesta</h2>
              <div style={{ display: "flex", gap: "0.4rem" }}>
                <CopyButton text={resultado.respuesta} />
                <VoiceControls modo="hablar" texto={resultado.respuesta} />
              </div>
            </div>
            <p>{resultado.respuesta}</p>
          </section>

          <section className="panel fragmentos-panel">
            <h2>Fragmentos citados (fuente original)</h2>
            {resultado.fragmentos.length === 0 && <p>No se encontraron fragmentos relevantes.</p>}
            {resultado.fragmentos.map((f, idx) => (
              <div className="fragmento" key={idx}>
                <div className="panel-header">
                  <div className="fragmento-fuente">
                    {f.fuente} · {f.area} · similitud {(f.score * 100).toFixed(0)}%
                  </div>
                  <CopyButton text={f.texto} label="Copiar" />
                </div>
                <p className="fragmento-texto">{f.texto}</p>
              </div>
            ))}
          </section>

          <div className="result-disclaimer">{resultado.disclaimer}</div>

          <DocumentGenerator />
        </div>
      )}
    </div>
  );
}
