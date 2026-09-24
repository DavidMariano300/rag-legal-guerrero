import { useState } from "react";
import { FontSize, Theme } from "../hooks/useSettings";

interface Props {
  theme: Theme;
  setTheme: (t: Theme) => void;
  fontSize: FontSize;
  setFontSize: (f: FontSize) => void;
}

const THEME_OPTIONS: { value: Theme; label: string }[] = [
  { value: "system", label: "Sistema" },
  { value: "light", label: "Claro" },
  { value: "dark", label: "Oscuro" },
];

const FONT_SIZE_OPTIONS: { value: FontSize; label: string }[] = [
  { value: "sm", label: "A-" },
  { value: "md", label: "A" },
  { value: "lg", label: "A+" },
];

export default function SettingsPanel({ theme, setTheme, fontSize, setFontSize }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="settings">
      <button
        type="button"
        className="settings-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-label="Preferencias de la interfaz"
        aria-expanded={open}
      >
        ⚙ Preferencias
      </button>

      {open && (
        <div className="settings-popover">
          <div className="settings-group">
            <span>Tema</span>
            <div className="settings-buttons">
              {THEME_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={theme === opt.value ? "active" : ""}
                  onClick={() => setTheme(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="settings-group">
            <span>Tamaño de texto</span>
            <div className="settings-buttons">
              {FONT_SIZE_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={fontSize === opt.value ? "active" : ""}
                  onClick={() => setFontSize(opt.value)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
