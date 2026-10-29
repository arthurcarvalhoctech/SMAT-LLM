"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("theme-light", theme === "light");
  document.documentElement.dataset.theme = theme;
}

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const stored = window.localStorage.getItem("smat-theme");
    const next: Theme = stored === "dark" ? "dark" : "light";
    setTheme(next);
    applyTheme(next);
  }, []);

  function toggleTheme() {
    const next: Theme = theme === "light" ? "dark" : "light";
    setTheme(next);
    applyTheme(next);
    window.localStorage.setItem("smat-theme", next);
  }

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={theme === "light" ? "Ativar tema escuro" : "Ativar tema claro"}
      className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2 text-xs text-slate-400 transition hover:border-white/20 hover:text-slate-200"
    >
      <span aria-hidden>{theme === "light" ? "☾" : "☀"}</span>
      <span className="hidden sm:inline">
        {theme === "light" ? "Escuro" : "Claro"}
      </span>
    </button>
  );
}
