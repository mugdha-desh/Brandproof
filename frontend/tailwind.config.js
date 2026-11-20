/** @type {import('tailwindcss').Config} */
const v = (n) => `rgb(var(--${n}) / <alpha-value>)`;
module.exports = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ["var(--font-body)", "system-ui", "sans-serif"], display: ["var(--font-display)", "system-ui", "sans-serif"] },
      colors: {
        navy: "#0B1B3A", ink: v("ink"), brand: "#0E7C7B", brandbg: v("brandbg"), stamp: "#C2331A", stampbg: v("stampbg"),
        paper: v("paper"), surface: v("surface"), ok: "#0B7A55", okbg: v("okbg"), warnbg: v("warnbg"), warn: "#7A4E00",
        slate: { 50: v("s50"), 100: v("s100"), 200: v("s200"), 300: v("s300"), 400: v("s400"), 500: v("s500"), 600: v("s600"), 700: v("s700"), 800: v("s800"), 900: v("s900") },
      },
      boxShadow: { lift: "0 2px 4px rgba(11,27,58,.06), 0 16px 32px -14px rgba(11,27,58,.22)", soft: "0 1px 2px rgba(11,27,58,.05), 0 8px 24px -12px rgba(11,27,58,.14)" },
    },
  },
  plugins: [],
};
