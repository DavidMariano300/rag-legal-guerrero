import { FormEvent, useEffect, useState } from "react";
import { generarDocumento, listarPlantillas, Plantilla } from "../api";

export default function DocumentGenerator() {
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [seleccionada, setSeleccionada] = useState<string>("");
  const [valores, setValores] = useState<Record<string, string>>({});
  const [generando, setGenerando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listarPlantillas()
      .then((data) => {
        setPlantillas(data);
        if (data.length > 0) setSeleccionada(data[0].id);
      })
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

  if (plantillas.length === 0) return null;

  return (
    <section className="panel" style={{ marginTop: "1.5rem" }}>
      <h2>Generar documento (mecanismo de prueba)</h2>
      <p style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
        Esto genera un documento .docx de ejemplo para validar el mecanismo. Todavía no incluye plantillas de
        documentos legales reales.
      </p>

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
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
