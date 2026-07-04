// Shared wildfire-demo design language (mirrored by the scenario UI):
// dark layered ink surfaces, a single ember severity ramp as the dominant
// accent, mono for telemetry / sans for labels. No webfonts: system stacks
// only, so the demo never fetches at runtime.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#0a0d11",
          900: "#0f1319",
          850: "#141a22",
          800: "#1a212b",
          700: "#232c38",
          600: "#2e3947",
          500: "#3d4a5c",
          400: "#5b6b80",
          300: "#8494a9",
          200: "#aab8c9",
          100: "#d6dee8",
          50: "#eef2f7",
        },
        ember: {
          300: "#ffd08a",
          400: "#ffb74a",
          500: "#ff8a3d",
          600: "#f4511e",
          700: "#d32f2f",
        },
        live: "#3fb950",
        dead: "#f85149",
        stale: "#d29922",
      },
      fontFamily: {
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      keyframes: {
        "feed-in": {
          "0%": { opacity: "0", transform: "translateY(-6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-dot": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.35" },
        },
      },
      animation: {
        "feed-in": "feed-in 240ms cubic-bezier(0.2, 0.7, 0.3, 1)",
        "pulse-dot": "pulse-dot 1.2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
