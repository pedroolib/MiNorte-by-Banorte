"use client";

import { useEffect, useRef, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";

type Theme = "light" | "dark";

const THEME_KEY = "minorte_theme";

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("light");
  const [mounted, setMounted] = useState(false);
  const transitionTimeout = useRef<number | null>(null);

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_KEY) as Theme | null;
    const preferred = window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
    const initial = stored === "dark" || stored === "light" ? stored : preferred;
    document.documentElement.classList.toggle("dark", initial === "dark");
    setTheme(initial);
    setMounted(true);

    return () => {
      if (transitionTimeout.current !== null) {
        window.clearTimeout(transitionTimeout.current);
      }
    };
  }, []);

  function toggleTheme() {
    const next = theme === "light" ? "dark" : "light";
    const root = document.documentElement;
    if (transitionTimeout.current !== null) {
      window.clearTimeout(transitionTimeout.current);
    }
    root.classList.add("theme-transition");
    root.classList.toggle("dark", next === "dark");
    transitionTimeout.current = window.setTimeout(() => {
      root.classList.remove("theme-transition");
      transitionTimeout.current = null;
    }, 240);
    window.localStorage.setItem(THEME_KEY, next);
    setTheme(next);
  }

  return (
    <Button
      type="button"
      variant="outline"
      size="icon"
      className="rounded-full border-border/70 bg-card/80 shadow-sm backdrop-blur"
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      title={theme === "dark" ? "Modo claro" : "Modo oscuro"}
    >
      {mounted && theme === "dark" ? (
        <Sun className="size-4" />
      ) : (
        <Moon className="size-4" />
      )}
    </Button>
  );
}
