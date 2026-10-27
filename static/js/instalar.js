// "Instalar o app": ícone do Quizify na tela inicial do celular.
// Android/Chrome/Edge: usa o pedido de instalação do navegador.
// iPhone/iPad (Safari): mostra como usar "Adicionar à Tela de Início".
(() => {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    const faixa = document.getElementById('instalar-app');
    if (!faixa) return;
    const botao = document.getElementById('instalar-botao');
    const fechar = document.getElementById('instalar-fechar');
    const ajudaIos = document.getElementById('instalar-ios');
    const CHAVE = 'quizify-instalar-dispensado';
    const TRINTA_DIAS = 30 * 24 * 3600 * 1000;

    const instalado = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    let dispensado = false;
    try { dispensado = Date.now() - Number(localStorage.getItem(CHAVE) || 0) < TRINTA_DIAS; } catch { /* sem armazenamento */ }
    if (instalado || dispensado) return;

    const ua = navigator.userAgent;
    const ehIos = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    let pedido = null;

    const mostrar = () => faixa.classList.remove('hidden');
    const esconder = () => faixa.classList.add('hidden');

    window.addEventListener('beforeinstallprompt', (evento) => {
        evento.preventDefault();      // guarda o pedido para o nosso botão
        pedido = evento;
        botao.textContent = 'Instalar';
        mostrar();
    });

    if (ehIos) {
        botao.textContent = 'Como instalar';
        mostrar();
    }

    botao.addEventListener('click', async () => {
        if (pedido) {
            pedido.prompt();
            const { outcome } = await pedido.userChoice;
            pedido = null;
            if (outcome === 'accepted') esconder();
        } else if (ehIos) {
            ajudaIos.classList.toggle('hidden');
        }
    });

    fechar.addEventListener('click', () => {
        try { localStorage.setItem(CHAVE, String(Date.now())); } catch { /* sem armazenamento */ }
        esconder();
    });

    window.addEventListener('appinstalled', esconder);
})();
