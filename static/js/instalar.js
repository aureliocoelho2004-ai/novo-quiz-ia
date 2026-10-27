// "Instalar o app": ícone do Quizify na tela inicial do celular.
// No celular a faixa aparece sempre (com o passo a passo pelo menu do navegador).
// Quando o Chrome/Edge libera o pedido de instalação, o botão passa a instalar direto.
(() => {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    }

    const faixa = document.getElementById('instalar-app');
    if (!faixa) return;
    const botao = document.getElementById('instalar-botao');
    const fechar = document.getElementById('instalar-fechar');
    const ajudas = {
        ios: document.getElementById('instalar-ios'),
        android: document.getElementById('instalar-android'),
        navegador: document.getElementById('instalar-navegador'),
    };
    const CHAVE = 'quizify-instalar-dispensado';
    const TRINTA_DIAS = 30 * 24 * 3600 * 1000;

    const instalado = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
    let dispensado = false;
    try { dispensado = Date.now() - Number(localStorage.getItem(CHAVE) || 0) < TRINTA_DIAS; } catch { /* sem armazenamento */ }
    if (instalado || dispensado) return;

    const ua = navigator.userAgent;
    const ehIos = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const ehAndroid = /Android/i.test(ua);
    // Navegadores embutidos (Instagram, Facebook, TikTok, LinkedIn...) não instalam apps.
    const dentroDeApp = /Instagram|FBAN|FBAV|FB_IAB|TikTok|musical_ly|LinkedInApp|Line\/|; wv\)/i.test(ua);
    const ajuda = dentroDeApp ? 'navegador' : ehIos ? 'ios' : ehAndroid ? 'android' : null;
    let pedido = null;

    const mostrar = () => faixa.classList.remove('hidden');
    const esconder = () => faixa.classList.add('hidden');
    const esconderAjudas = () => Object.values(ajudas).forEach((el) => el && el.classList.add('hidden'));

    window.addEventListener('beforeinstallprompt', (evento) => {
        evento.preventDefault();      // guarda o pedido para o nosso botão
        pedido = evento;
        botao.textContent = 'Instalar';
        esconderAjudas();
        mostrar();
    });

    if (ajuda) {                      // celular: mostra já, com o passo a passo
        botao.textContent = 'Como instalar';
        mostrar();
    }

    botao.addEventListener('click', async () => {
        if (pedido) {
            pedido.prompt();
            const { outcome } = await pedido.userChoice;
            pedido = null;
            if (outcome === 'accepted') esconder();
        } else if (ajuda && ajudas[ajuda]) {
            ajudas[ajuda].classList.toggle('hidden');
        }
    });

    fechar.addEventListener('click', () => {
        try { localStorage.setItem(CHAVE, String(Date.now())); } catch { /* sem armazenamento */ }
        esconder();
    });

    window.addEventListener('appinstalled', esconder);
})();
