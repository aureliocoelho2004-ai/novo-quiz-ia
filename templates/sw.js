// Service worker do Quizify (app instalável).
// Não guarda páginas em cache: o app depende do login e dos dados atuais.
// Só mostra um aviso amigável quando o celular está sem internet.
const VERSAO = 'quizify-v2';

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (evento) => evento.waitUntil(self.clients.claim()));

const PAGINA_OFFLINE = `<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Sem internet - Quizify</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;
background:#160B29;color:#f1f5f9;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;text-align:center}
.c{max-width:360px;background:#24133E;border:1px solid #3D2766;border-radius:16px;padding:28px}
h1{font-size:1.3rem;margin:12px 0 8px}p{color:#B9A8D9;line-height:1.5}
button{margin-top:16px;width:100%;padding:13px;border:0;border-radius:12px;background:#C1FC38;color:#24133E;
font:inherit;font-weight:700;cursor:pointer}</style></head>
<body><div class="c"><div style="font-size:3rem">📡</div><h1>Sem ligação à internet</h1>
<p>O Quizify precisa de internet para criar e abrir os seus quizzes. Verifique a ligação e tente de novo.</p>
<button onclick="location.reload()">Tentar novamente</button></div></body></html>`;

self.addEventListener('fetch', (evento) => {
    if (evento.request.mode !== 'navigate') return;  // arquivos e API: comportamento normal
    evento.respondWith(
        fetch(evento.request).catch(() => new Response(PAGINA_OFFLINE, {
            headers: { 'Content-Type': 'text/html; charset=utf-8' },
        }))
    );
});
