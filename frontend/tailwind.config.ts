import type { Config } from "tailwindcss";

// Bloomberg-terminal-on-dark palette tuned for the stat-arb dashboards we're
// modelling on: deep blacks, neon accents, fluorescent green/red for PnL,
// and a single subtle border colour so dense numeric layouts read cleanly.
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#000000",
          panel: "#0a0a0a",
          card: "#111111",
          elevated: "#1a1a1a",
        },
        border: {
          subtle: "#1f1f1f",
          muted: "#2a2a2a",
        },
        text: {
          primary: "#e6e6e6",
          secondary: "#9ca3af",
          muted: "#6b7280",
          faint: "#4b5563",
        },
        accent: {
          cyan: "#00d4ff",
          magenta: "#ff2ad4",
          green: "#00ff88",
          red: "#ff3355",
          purple: "#a855f7",
          yellow: "#facc15",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "'Fira Code'", "ui-monospace", "monospace"],
      },
      fontSize: {
        // Trading UIs lean small; these are the steps the dashboards use.
        "2xs": ["10px", { lineHeight: "14px" }],
        xs: ["11px", { lineHeight: "16px" }],
        sm: ["12px", { lineHeight: "18px" }],
      },
      gridTemplateColumns: {
        kpi: "repeat(auto-fit, minmax(96px, 1fr))",
      },
    },
  },
  plugins: [],
};

export default config;
