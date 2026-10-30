// Olhinho nos campos de senha: toca para ver ou esconder o que digitou.
(() => {
    const OLHO = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
    const OLHO_FECHADO = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.9 17.9A10.4 10.4 0 0 1 12 19c-6.5 0-10-7-10-7a18.5 18.5 0 0 1 5.1-5.9M9.9 5.2A9.6 9.6 0 0 1 12 5c6.5 0 10 7 10 7a18.6 18.6 0 0 1-2.2 3.2"/><path d="M14.1 14.1a3 3 0 1 1-4.2-4.2"/><path d="M2 2l20 20"/></svg>';

    document.querySelectorAll('input[type="password"]').forEach((campo) => {
        campo.dataset.senha = '1';
        const caixa = document.createElement('div');
        caixa.style.position = 'relative';
        // em linha com um botão (ex.: admin), a caixa ocupa o lugar do campo
        if (getComputedStyle(campo.parentElement).display === 'flex') caixa.style.cssText += 'flex:1;min-width:0';
        campo.parentNode.insertBefore(caixa, campo);
        caixa.appendChild(campo);
        campo.style.paddingRight = '3rem';

        const botao = document.createElement('button');
        botao.type = 'button';
        botao.innerHTML = OLHO;
        botao.setAttribute('aria-label', 'Mostrar senha');
        botao.style.cssText = 'position:absolute;top:0;right:0;bottom:0;width:3rem;display:flex;align-items:center;'
            + 'justify-content:center;background:none;border:0;color:#94a3b8;cursor:pointer';
        botao.addEventListener('click', () => {
            const mostrar = campo.type === 'password';
            campo.type = mostrar ? 'text' : 'password';
            botao.innerHTML = mostrar ? OLHO_FECHADO : OLHO;
            botao.setAttribute('aria-label', mostrar ? 'Esconder senha' : 'Mostrar senha');
        });
        caixa.appendChild(botao);
    });

    // ao enviar, volta a esconder: assim o navegador oferece salvar a senha normalmente
    document.addEventListener('submit', (e) => {
        e.target.querySelectorAll('input[data-senha]').forEach((c) => { c.type = 'password'; });
    }, true);
})();
