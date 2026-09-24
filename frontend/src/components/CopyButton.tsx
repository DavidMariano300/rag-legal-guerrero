import { useState } from "react";

interface Props {
  text: string;
  label?: string;
}

export default function CopyButton({ text, label = "Copiar" }: Props) {
  const [copiado, setCopiado] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1500);
    } catch {
      setCopiado(false);
    }
  }

  return (
    <button type="button" className="copy-button" onClick={handleCopy}>
      {copiado ? "¡Copiado!" : label}
    </button>
  );
}
