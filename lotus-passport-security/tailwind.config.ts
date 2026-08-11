import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "#f6f5f2",
        surface: "#ffffff",
        ink: {
          DEFAULT: "#1b1a17",
          soft: "#3a3833",
          muted: "#72706a",
        },
        line: "#e9e5dd",
        accent: {
          DEFAULT: "#d9543f",
          soft: "#fbeae5",
          ink: "#a8331f",
        },
        success: {
          DEFAULT: "#2f9e6f",
          soft: "#e4f5ec",
        },
        warn: {
          DEFAULT: "#c98a1b",
          soft: "#fbf0d8",
        },
        danger: {
          DEFAULT: "#d23b3b",
          soft: "#fbe6e6",
        },
        panel: "#15140f",
        panelSoft: "#26241c",
      },
      fontFamily: {
        sans: ["var(--font-geist-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-geist-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        "4xl": "2rem",
      },
      boxShadow: {
        soft: "0 1px 2px rgba(27,26,23,0.04), 0 8px 30px -12px rgba(27,26,23,0.12)",
        lift: "0 2px 6px rgba(27,26,23,0.06), 0 24px 60px -24px rgba(27,26,23,0.22)",
        glass: "inset 0 1px 0 rgba(255,255,255,0.5), 0 10px 40px -16px rgba(27,26,23,0.18)",
      },
      keyframes: {
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        floaty: {
          "0%,100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
      animation: {
        shimmer: "shimmer 1.6s infinite",
        floaty: "floaty 6s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
