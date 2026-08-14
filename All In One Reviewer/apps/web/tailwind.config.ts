import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        graphite: "var(--graphite)",
        mist: "var(--matrix-mist)",
        orchid: "var(--orchid-ink)",
        amber: "var(--signal-amber)",
        teal: "var(--vector-teal)",
        carmine: "var(--error-carmine)",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        body: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
    },
  },
  plugins: [],
};

export default config;
