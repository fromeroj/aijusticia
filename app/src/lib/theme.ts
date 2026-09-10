/**
 * Theme — dark/light mode con persistencia.
 * Usa la clase `dark` en <html> (convención Tailwind).
 * Detecta preferencia del sistema la primera vez.
 */
import { useCallback, useEffect, useState } from "react";

const KEY = "aij_theme";
let current: "light" | "dark" = "light";
const listeners = new Set<(t: "light" | "dark") => void>();

export function getTheme(): "light" | "dark" {
  if (typeof window !== "undefined" && !current) {
    const saved = localStorage.getItem(KEY) as "light" | "dark" | null;
    current = saved ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    document.documentElement.classList.toggle("dark", current === "dark");
  }
  return current;
}

export function setTheme(t: "light" | "dark") {
  current = t;
  if (typeof window !== "undefined") {
    localStorage.setItem(KEY, t);
    document.documentElement.classList.toggle("dark", t === "dark");
  }
  listeners.forEach((fn) => fn(t));
}

export function toggleTheme() {
  setTheme(getTheme() === "dark" ? "light" : "dark");
}

export function useTheme(): ["light" | "dark", () => void] {
  const [theme, setThemeState] = useState<"light" | "dark">(getTheme());
  useEffect(() => {
    const fn = (t: "light" | "dark") => setThemeState(t);
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  }, []);
  const toggle = useCallback(() => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    setThemeState(next);
  }, [theme]);
  return [theme, toggle];
}
