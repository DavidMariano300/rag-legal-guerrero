import { ChangeEvent, useEffect, useRef, useState } from "react";
import { borrarDocumentosSesion, subirDocumento } from "../api";

interface Props {
  sessionId: string;
  onHasDocuments: (hasDocuments: boolean) => void;
}

interface ArchivoSubido {
  filename: string;
  fragmentos_indexados: number;
}

export default function DocumentUpload({ sessionId, onHasDocuments }: Props) {
  const [archivos, setArchivos] = useState<ArchivoSubido[]>([]);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    onHasDocuments(archivos.length > 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [archivos]);

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setSubiendo(true);
    setError(null);
    try {
      const resultado = await subirDocumento(sessionId, file);
      setArchivos((prev) => [...prev, resultado]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al subir el documento.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function quitarArchivo(filename: string) {
    if (archivos.length === 1) {
      await borrarDocumentosSesion(sessionId).catch(() => null);
      setArchivos([]);
      return;
    }
    // Con un solo documento a la vez alcanza para el MVP; si hay varios, se limpian todos.
    await borrarDocumentosSesion(sessionId).catch(() => null);
    setArchivos((prev) => prev.filter((a) => a.filename !== filename));
  }

  return (
    <div className="attach-control">
      <button
        type="button"
        className="icon-button"
        onClick={() => inputRef.current?.click()}
        disabled={subiendo}
        aria-label="Adjuntar documento"
        title="Adjuntar documento (PDF, Word o texto)"
      >
        {subiendo ? (
          "…"
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
            <path d="M20 11.5l-7.8 7.8a5 5 0 01-7.1-7.1l8.5-8.5a3.3 3.3 0 014.7 4.7l-8.5 8.5a1.7 1.7 0 01-2.4-2.4l7.8-7.8" />
          </svg>
        )}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt"
        onChange={handleFileChange}
        style={{ display: "none" }}
      />

      {archivos.length > 0 && (
        <div className="attach-chips">
          {archivos.map((a) => (
            <span className="chip" key={a.filename} title={`${a.fragmentos_indexados} fragmentos indexados`}>
              <span className="chip-nombre">{a.filename}</span>
              <button type="button" onClick={() => quitarArchivo(a.filename)} aria-label={`Quitar ${a.filename}`}>
                ✕
              </button>
            </span>
          ))}
        </div>
      )}

      {error && (
        <div className="error-panel">
          {error}
        </div>
      )}
    </div>
  );
}
