import { FormEvent, useEffect, useRef, useState } from "react";
import { consultar, QueryResponse } from "./api";
import { clearToken, getToken } from "./auth";
import { useSettings } from "./hooks/useSettings";
import SettingsPanel from "./components/SettingsPanel";
import CopyButton from "./components/CopyButton";
import DocumentUpload from "./components/DocumentUpload";
import VoiceControls from "./components/VoiceControls";
import DocumentGenerator from "./components/DocumentGenerator";
import Login from "./components/Login";
import { getSessionId } from "./session";

const AREAS = [
  { value: "", label: "Todas las áreas" },
  { value: "Civil y Familiar", label: "Civil y Familiar" },
  { value: "Penal", label: "Penal" },
  { value: "Laboral", label: "Laboral" },
  { value: "Laboral burocrático", label: "Laboral (servidores públicos)" },
  { value: "Administrativo y Fiscal", label: "Administrativo y Fiscal" },
  { value: "Constitucional y Electoral", label: "Constitucional y Electoral" },
  { value: "Amparo", label: "Amparo" },
];

// Resalta las citas literales «…» (lo que el abogado puede cotejar contra el artículo) y convierte las
// negritas **…** que a veces escribe el modelo, que si no se verían como asteriscos.
function conCitas(texto: string) {
  return texto.split(/(«[^»]+»|\*\*[^*]+\*\*)/g).map((parte, i) =>
    parte.startsWith("«") ? (
      <q key={i} className="cita">{parte.slice(1, -1)}</q>
    ) : parte.startsWith("**") ? (
      <strong key={i}>{parte.slice(2, -2)}</strong>
    ) : (
      parte
    ),
  );
}

// "Artículo 87, LEY FEDERAL DEL TRABAJO" → ["Artículo 87", "LEY FEDERAL DEL TRABAJO"]
function separarFuente(fuente: string): [string, string] {
  const i = fuente.indexOf(", ");
  return i === -1 ? [fuente, ""] : [fuente.slice(0, i), fuente.slice(i + 2)];
}

export default function App() {
  const { theme, setTheme, fontSize, setFontSize } = useSettings();
  const sessionId = getSessionId();
  const [autenticado, setAutenticado] = useState(() => !!getToken());

  const [pregunta, setPregunta] = useState("");
  const [area, setArea] = useState("");
  const [hasDocuments, setHasDocuments] = useState(false);
  const [resultado, setResultado] = useState<QueryResponse | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultadoRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (resultado) resultadoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [resultado]);

  // Segundos de espera a la vista: en el servidor sin GPU una respuesta tarda 1–2 min y sin contador parece trabada.
  const [segundos, setSegundos] = useState(0);
  useEffect(() => {
    if (!cargando) return;
    setSegundos(0);
    const id = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [cargando]);

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
      if (!getToken()) setAutenticado(false);
    } finally {
      setCargando(false);
    }
  }

  function handleLogout() {
    clearToken();
    setAutenticado(false);
    setResultado(null);
  }

  if (!autenticado) {
    return <Login onAuthenticated={() => setAutenticado(true)} />;
  }

  return (
    <>
      <header className="sitio-cabecera">
        <p className="logotipo">Amate</p>
        <div className="sitio-acciones">
          <SettingsPanel theme={theme} setTheme={setTheme} fontSize={fontSize} setFontSize={setFontSize} />
          <button type="button" className="enlace" onClick={handleLogout}>
            Cerrar sesión
          </button>
        </div>
      </header>

      <main>
        <section className="portada">
          <div className="marco">
            <h1>Pregunta por las leyes de Guerrero y lee el artículo en que se basa la respuesta.</h1>
            <p>
              Más de 150 leyes y códigos del Congreso del Estado, además de leyes federales como la Ley Federal del
              Trabajo. Escribe la pregunta como se la harías a un colega.
            </p>
          </div>
        </section>

        <section className="banda">
          <div className="marco">
            <form className="tarjeta" onSubmit={handleSubmit}>
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
                  placeholder="Ej. Trabajé 6 meses y ganaba $500 diarios, ¿cuánto me toca de aguinaldo?"
                  rows={4}
                />
              </label>

              <div className="composer-toolbar">
                <div className="composer-toolbar-left">
                  <DocumentUpload sessionId={sessionId} onHasDocuments={setHasDocuments} />
                  <VoiceControls onTranscribed={(texto) => setPregunta((prev) => (prev ? `${prev} ${texto}` : texto))} />
                </div>
                <button type="submit" className="primary-button" disabled={cargando || !pregunta.trim()}>
                  {cargando ? "Consultando…" : "Consultar"}
                </button>
              </div>

              <div aria-live="polite">
                {cargando && (
                  <div className="espera">
                    <div className="espera-barra" />
                    Buscando en la legislación y redactando la respuesta <span aria-hidden="true">({segundos} s)</span>. Puede tardar un par de minutos.
                  </div>
                )}
                {error && <div className="error-panel">{error}</div>}
              </div>

              <p className="aviso-ia">
                Amate usa inteligencia artificial y puede cometer errores u omisiones. Verifica siempre la información
                contra la fuente original antes de usarla en cualquier trámite o gestión legal.
              </p>
            </form>
          </div>
        </section>

        {resultado && (
          <section className="resultado marco" ref={resultadoRef}>
            <div className="panel-header">
              <h2>Respuesta</h2>
              <div className="acciones">
                <CopyButton text={resultado.respuesta} />
                <VoiceControls modo="hablar" texto={resultado.respuesta} />
              </div>
            </div>
            <p className="respuesta">{conCitas(resultado.respuesta)}</p>
            <p className="aviso-resultado">{resultado.disclaimer}</p>

            {resultado.plantilla_sugerida && <DocumentGenerator sugerencia={resultado.plantilla_sugerida} />}

            <h2 className="fuentes-titulo">Artículos consultados</h2>
            {resultado.fragmentos.length === 0 ? (
              <p>No se encontraron artículos relacionados con la pregunta.</p>
            ) : (
              <ol className="fuentes">
                {resultado.fragmentos.map((f, idx) => {
                  const [articulo, ley] = separarFuente(f.fuente);
                  return (
                    <li className="fuente" key={idx}>
                      <div className="fuente-cabecera">
                        <div>
                          <p className="fuente-articulo">{articulo}</p>
                          {ley && <p className="fuente-ley">{ley}</p>}
                          <p className="fuente-meta">
                            {f.area}, similitud {(f.score * 100).toFixed(0)} %
                          </p>
                        </div>
                        <CopyButton text={f.texto} />
                      </div>
                      <p className="fragmento-texto">{f.texto}</p>
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
        )}
      </main>
    </>
  );
}
