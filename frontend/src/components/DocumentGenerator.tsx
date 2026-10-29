import { FormEvent, useEffect, useState } from "react";
import { generarDocumento, listarPlantillas, Plantilla, PlantillaSugerida } from "../api";

interface Props {
  sugerencia: PlantillaSugerida;
}

export default function DocumentGenerator({ sugerencia }: Props) {
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [expandido, setExpandido] = useState(false);
  const [seleccionada, setSeleccionada] = useState<string>(sugerencia.id);
  const [valores, setValores] = useState<Record<string, string>>({});
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarPlantillas()
      .then(setPlantillas)
      .catch(() => setError("No se pudieron cargar las plantillas de documentos."));
  }, []);

  const plantillaActual = plantillas.find((p) => p.id === seleccionada);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!plantillaActual) return;

    setGenerando(true);
    setError(null);
    try {
      const blob = await generarDocumento(plantillaActual.id, valores);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${plantillaActual.id}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al generar el documento.");
    } finally {
      setGenerando(false);
    }
  }

  if (!expandido) {
    return (
      <div className="doc-suggestion">
        <span>Puedes generar un borrador de {sugerencia.nombre} en Word a partir de esta consulta.</span>
        <button type="button" className="boton-secundario" onClick={() => setExpandido(true)}>
          Generar documento
        </button>
      </div>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Generar documento (mecanismo de prueba)</h2>
        <button type="button" className="boton-secundario" onClick={() => setExpandido(false)}>
          Cerrar
        </button>
      </div>
      <p className="panel-nota">
        Esto genera un documento .docx de ejemplo para validar el mecanismo. Todavía no incluye plantillas de
        documentos legales reales.
      </p>

      <form onSubmit={handleSubmit} className="generador">
        <label className="field">
          <span>Tipo de documento</span>
          <select value={seleccionada} onChange={(e) => setSeleccionada(e.target.value)}>
            {plantillas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nombre}
              </option>
            ))}
          </select>
        </label>

        {plantillaActual?.campos.map((campo) => (
          <label className="field" key={campo.nombre}>
            <span>
              {campo.etiqueta}
              {campo.requerido ? " *" : ""}
            </span>
            <input
              type={campo.tipo === "fecha" ? "date" : campo.tipo === "numero" ? "number" : "text"}
              value={valores[campo.nombre] || ""}
              onChange={(e) => setValores((prev) => ({ ...prev, [campo.nombre]: e.target.value }))}
              required={campo.requerido}
            />
          </label>
        ))}

        {error && <div className="error-panel">{error}</div>}

        <button type="submit" className="primary-button" disabled={generando}>
          {generando ? "Generando..." : "Generar y descargar"}
        </button>
      </form>
    </section>
  );
}
