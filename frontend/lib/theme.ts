export const THEME_KEY = "bp_theme";

// Runs before first paint (see app/layout.tsx) so there is no flash of the wrong theme.
export const THEME_SCRIPT = `try{var t=localStorage.getItem("${THEME_KEY}");if(!t&&window.matchMedia("(prefers-color-scheme: dark)").matches)t="dark";if(t==="dark")document.documentElement.classList.add("dark")}catch(e){}`;
