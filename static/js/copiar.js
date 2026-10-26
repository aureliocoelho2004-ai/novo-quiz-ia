// Botões "Copiar link" (qualquer elemento com data-copiar="<texto>").
document.addEventListener('click', async (evento) => {
    const botao = evento.target.closest('[data-copiar]');
    if (!botao) return;
    const texto = botao.dataset.copiar;
    try {
        await navigator.clipboard.writeText(texto);
    } catch {
        const campo = Object.assign(document.createElement('textarea'), { value: texto });
        document.body.appendChild(campo);
        campo.select();
        document.execCommand('copy');
        campo.remove();
    }
    const original = botao.textContent;
    botao.textContent = 'Copiado!';
    setTimeout(() => { botao.textContent = original; }, 1500);
});
