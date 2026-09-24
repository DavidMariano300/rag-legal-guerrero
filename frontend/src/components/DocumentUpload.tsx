import { ChangeEvent, useRef, useState } from "react";
import { borrarDocumentosSesion, subirDocumento } from "../api";

interface Props {
  sessionId: string;
  usarDocumentos: boolean;
  setUsarDocumentos: (v: boolean) => void;
}

interface ArchivoSubido {
  filename: string;
  fragmentos_indexados: number;
}

export default function DocumentUpload({ sessionId, usarDocumentos, setUsarDocumentos }: Props) {
  const [archivos, setArchivos] = useState<ArchivoSubido[]>([]);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setSubiendo(true);
    setError(null);
    try {
      const resultado = await subirDocumento(sessionId, file);
      setArchivos((prev) => [...prev, resultado]);
      setUsarDocumentos(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al subir el documento.");
    } finally {
      setSubiendo(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function handleClearAll() {
    await borrarDocumentosSesion(sessionId).catch(() => null);
    setArchivos([]);
    setUsarDocumentos(false);
  }

  return (
    <div className="field">
      <span>Documentos de esta consulta (opcional)</span>

      <input ref={inputRef} type="file" accept=".pdf,.docx,.txt" onChange={handleFileChange} disabled={subiendo} />

      {error && <div className="error-panel">{error}</div>}

      {archivos.length > 0 && (
        <>
          <div className="upload-list">
            {archivos.map((a, idx) => (
              <div className="upload-item" key={idx}>
                <span>
                  {a.filename} ({a.fragmentos_indexados} fragmentos)
                </span>
              </div>
            ))}
          </div>

          <label className="checkbox-row">
            <input type="checkbox" checked={usarDocumentos} onChange={(e) => setUsarDocumentos(e.target.checked)} />
            Incluir estos documentos en la búsqueda
          </label>

          <button type="button" className="copy-button" onClick={handleClearAll}>
            Quitar todos los documentos de esta sesión
          </button>
        </>
      )}

      <small style={{ color: "var(--muted)" }}>
        Los documentos subidos solo se usan en esta sesión de tu navegador, no se agregan al corpus legal
        permanente ni son visibles para otros usuarios.
      </small>
    </div>
  );
}
