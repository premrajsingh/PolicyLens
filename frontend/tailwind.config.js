/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef9f9",
          100: "#d5f0f1",
          200: "#aee1e3",
          300: "#79cbd0",
          400: "#3aadb4",
          500: "#0d7377",
          600: "#0d7377",
          700: "#0d7377",
          800: "#095456",
          900: "#074345",
          950: "#042b2d",
        },
        navy: {
          DEFAULT: "#0B1F3A",
          50: "#eef3f8",
          100: "#d5e0ec",
          700: "#0B1F3A",
          800: "#08162b",
          900: "#050f1d",
        },
        surface: {
          DEFAULT: "rgb(var(--surface) / <alpha-value>)",
          raised: "rgb(var(--surface-raised) / <alpha-value>)",
          muted: "rgb(var(--surface-muted) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--ink) / <alpha-value>)",
          muted: "rgb(var(--ink-muted) / <alpha-value>)",
          faint: "rgb(var(--ink-faint) / <alpha-value>)",
        },
        border: {
          DEFAULT: "rgb(var(--border) / <alpha-value>)",
          strong: "rgb(var(--border-strong) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: [
          "DM Sans",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "sans-serif",
        ],
        headline: [
          "DM Sans",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(11 31 58 / 0.04), 0 1px 3px 0 rgb(11 31 58 / 0.06)",
        "card-hover":
          "0 4px 12px -2px rgb(11 31 58 / 0.08), 0 2px 4px -2px rgb(11 31 58 / 0.04)",
      },
    },
  },
  plugins: [],
};
