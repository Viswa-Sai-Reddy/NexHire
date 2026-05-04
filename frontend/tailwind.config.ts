import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * NexHire design tokens.
 *
 * Colors and stage palette are locked from the UI sample (see
 * `docs/Implementation_Plan.md` → "UI Design Reference"). The shadcn
 * `--primary` / `--secondary` / `--accent` semantic tokens are wired
 * via CSS variables in `src/index.css`; raw stage colors live here for
 * direct use in pipeline visualizations and status pills.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Stage palette — mirrors `docs/Implementation_Plan.md` lock.
        stage: {
          submitted: "hsl(217 91% 60%)",   // blue-500
          review: "hsl(38 92% 50%)",       // amber-500
          onboarding: "hsl(239 84% 67%)",  // indigo-500
          nda: "hsl(258 90% 66%)",         // violet-500
          active: "hsl(160 84% 39%)",      // emerald-500
          extended: "hsl(173 80% 40%)",    // teal-500
          closure: "hsl(215 16% 47%)",     // slate-500
          rejected: "hsl(347 77% 50%)",    // rose-500
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      backgroundImage: {
        "hero-gradient":
          "linear-gradient(135deg, hsl(220 40% 8%) 0%, hsl(220 30% 18%) 100%)",
      },
    },
  },
  plugins: [animate],
};

export default config;
