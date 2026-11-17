// CSS do app gerado no build (antes vinha do Tailwind Play CDN e bloqueava a renderização).
// Rebuild: npm run css   (gera static/css/app.css; commitar o arquivo gerado)
// As cores vêm de variáveis CSS definidas em templates/base.html (uma lista por tema).
const cor = (v) => `rgb(var(--${v}) / <alpha-value>)`;
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js", "./app.py"],
  // Classes que o JavaScript monta ou troca em tempo de execução
  safelist: ["hidden", "text-red-400", "text-amber-300", "text-green-400", "text-slate-300", "text-slate-400",
             "border-green-500", "bg-green-900/40", "bg-green-900/30", "border-red-500", "bg-red-900/40", "bg-slate-800"],
  theme: {
    extend: {
      colors: {
        slate: Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((n) => [n, cor("s" + n)])),
        lima: { DEFAULT: cor("lima"), claro: cor("lima-claro") },
        roxo: "#5920AB",
        tinta: cor("tinta"),
      },
      fontFamily: { sans: ["Jakarta", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
    },
  },
};
