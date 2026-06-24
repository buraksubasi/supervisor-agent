import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0f1117",
          secondary: "#1a1d27",
          tertiary: "#232735",
          border: "#2e3347",
        },
        accent: {
          DEFAULT: "#6366f1",
          hover: "#818cf8",
        },
      },
      typography: {
        DEFAULT: {
          css: {
            color: "#e2e8f0",
            a: { color: "#818cf8" },
            strong: { color: "#f1f5f9" },
            code: { color: "#a5b4fc", background: "#1e2133", padding: "2px 6px", borderRadius: "4px" },
            "pre code": { background: "transparent", padding: 0 },
            pre: { background: "#1e2133" },
            h1: { color: "#f1f5f9" },
            h2: { color: "#f1f5f9" },
            h3: { color: "#f1f5f9" },
            th: { color: "#f1f5f9" },
            blockquote: { color: "#94a3b8", borderLeftColor: "#6366f1" },
          },
        },
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
};

export default config;
