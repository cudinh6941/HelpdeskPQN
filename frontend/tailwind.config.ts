import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      colors: {
        border: "var(--border)",
        "border-subtle": "var(--border-subtle)",
        input: "var(--input)",
        ring: "var(--ring)",
        background: "var(--background)",
        foreground: "var(--foreground)",
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          foreground: "var(--accent-foreground)",
        },
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        faint: "var(--ink-faint)",
        sla: {
          urgent: "var(--sla-urgent-bg)",
          "urgent-fg": "var(--sla-urgent-fg)",
          neutral: "var(--sla-neutral-bg)",
          "neutral-fg": "var(--sla-neutral-fg)",
          breached: "var(--sla-breached-bg)",
          "breached-fg": "var(--sla-breached-fg)",
        },
        tier: {
          enterprise: "var(--tier-enterprise)",
          pro: "var(--tier-pro)",
          free: "var(--tier-free)",
        },
        note: {
          DEFAULT: "var(--note-bg)",
          border: "var(--note-border)",
          ink: "var(--note-ink)",
        },
      },
      borderRadius: {
        xs: "4px",
        sm: "6px",
        md: "8px",
        lg: "10px",
        xl: "12px",
      },
      boxShadow: {
        popover:
          "0 8px 24px -4px rgba(23,24,28,0.10), 0 0 0 1px rgba(23,24,28,0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
