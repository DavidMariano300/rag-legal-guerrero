import { useRef, useState } from "react";
import { hablarTexto, transcribirAudio } from "../api";
import { getSessionId } from "../session";

interface Props {
  modo?: "dictar" | "hablar";
  onTranscribed?: (texto: string) => void;
  texto?: string;
}

export default function VoiceControls({ modo = "dictar", onTranscribed, texto }: Props) {
  const [grabando, setGrabando] = useState(false);
  const [procesando, setProcesando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  async function iniciarGrabacion() {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (e) => chunksRef.current.push(e.data);
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
        setProcesando(true);
        try {
          const texto = await transcribirAudio(getSessionId(), audioBlob);
          onTranscribed?.(texto);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Error al transcribir el audio.");
        } finally {
          setProcesando(false);
        }
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setGrabando(true);
    } catch {
      setError("No se pudo acceder al micrófono. Verifica los permisos del navegador.");
    }
  }

  function detenerGrabacion() {
    mediaRecorderRef.current?.stop();
    setGrabando(false);
  }

  async function reproducirRespuesta() {
    if (!texto) return;
    setError(null);
    setProcesando(true);
    try {
      const audioBlob = await hablarTexto(texto);
      const url = URL.createObjectURL(audioBlob);
      const audio = new Audio(url);
      audio.onended = () => URL.revokeObjectURL(url);
      await audio.play();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error al generar el audio de la respuesta.");
    } finally {
      setProcesando(false);
    }
  }

  if (modo === "hablar") {
    return (
      <>
        <button type="button" className="copy-button" onClick={reproducirRespuesta} disabled={procesando}>
          {procesando ? "Generando audio..." : "🔊 Escuchar"}
        </button>
        {error && <span style={{ fontSize: "0.75rem", color: "var(--error-text)" }}>{error}</span>}
      </>
    );
  }

  return (
    <div>
      <button
        type="button"
        className={`icon-button ${grabando ? "recording" : ""}`}
        onClick={grabando ? detenerGrabacion : iniciarGrabacion}
        disabled={procesando}
        aria-label={grabando ? "Detener grabación" : "Dictar pregunta por voz"}
        title={grabando ? "Detener grabación" : "Dictar por voz"}
      >
        {procesando ? "..." : grabando ? "⏹" : "🎤"}
      </button>
      {error && (
        <div className="error-panel" style={{ marginTop: "0.5rem" }}>
          {error}
        </div>
      )}
    </div>
  );
}
