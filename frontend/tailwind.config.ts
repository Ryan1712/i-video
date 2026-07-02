import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
      },
      colors: {
        background: "var(--bg-base)",
        foreground: "var(--foreground)",
        accent: {
          DEFAULT: "#6366F1",
          light: "#818CF8",
          hover: "#4F46E5",
        },
        surface: {
          DEFAULT: "rgba(255, 255, 255, 0.03)",
          hover: "rgba(255, 255, 255, 0.055)",
        },
        border: {
          DEFAULT: "rgba(255, 255, 255, 0.08)",
          accent: "rgba(99, 102, 241, 0.3)",
        },
        muted: "#8A8F98",
        faint: "#4A4F5A",
      },
      borderRadius: {
        sm: "8px",
        DEFAULT: "12px",
        lg: "16px",
        xl: "24px",
      },
      boxShadow: {
        glow: "0 0 32px rgba(99,102,241,0.18), 0 0 80px rgba(99,102,241,0.08)",
        "glow-sm": "0 0 16px rgba(99,102,241,0.18)",
        card: "0 1px 1px rgba(0,0,0,0.3), 0 4px 16px rgba(0,0,0,0.2)",
      },
      animation: {
        "fade-up": "fade-up 0.6s cubic-bezier(0.16,1,0.3,1) both",
        "fade-in": "fade-in 0.5s ease both",
        "blob-float": "blob-float 8s ease-in-out infinite",
        shimmer: "shimmer 2.5s linear infinite",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(24px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "blob-float": {
          "0%, 100%": { transform: "translate(0,0) scale(1)" },
          "33%": { transform: "translate(20px,-15px) scale(1.05)" },
          "66%": { transform: "translate(-15px,10px) scale(0.96)" },
        },
        shimmer: {
          from: { backgroundPosition: "-200% center" },
          to: { backgroundPosition: "200% center" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
