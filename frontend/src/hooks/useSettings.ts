import { useEffect, useState } from "react";

export type Theme = "system" | "light" | "dark";
export type FontSize = "sm" | "md" | "lg";

const THEME_KEY = "rag_theme";
const FONT_SIZE_KEY = "rag_font_size";

function resolveTheme(theme: Theme): "light" | "dark" {
  if (theme === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return theme;
}

export function useSettings() {
  const [theme, setTheme] = useState<Theme>(() => (localStorage.getItem(THEME_KEY) as Theme) || "system");
  const [fontSize, setFontSize] = useState<FontSize>(
    () => (localStorage.getItem(FONT_SIZE_KEY) as FontSize) || "md",
  );

  useEffect(() => {
    const apply = () => {
      document.documentElement.dataset.theme = resolveTheme(theme);
    };
    apply();

    if (theme === "system") {
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      media.addEventListener("change", apply);
      return () => media.removeEventListener("change", apply);
    }
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.fontSize = fontSize;
  }, [fontSize]);

  useEffect(() => {
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    localStorage.setItem(FONT_SIZE_KEY, fontSize);
  }, [fontSize]);

  return { theme, setTheme, fontSize, setFontSize };
}
