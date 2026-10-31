// Seletor de cores (🎨): o tema fica guardado só neste celular/navegador.
(() => {
    const folha = document.getElementById('temas');
    const abrir = document.getElementById('temas-abrir');
    if (!folha || !abrir) return;
    const CHAVE = 'quizify-tema';
    const raiz = document.documentElement;
    const barra = document.getElementById('cor-barra');

    const atual = () => raiz.dataset.tema || 'quizify';
    function marcar() {
        folha.querySelectorAll('[data-tema]').forEach((b) => {
            const sel = b.dataset.tema === atual();
            b.setAttribute('aria-pressed', sel);
            const bolinha = b.querySelector('.tema-bolinha');
            bolinha.textContent = sel ? '✓' : '';
            bolinha.style.boxShadow = sel ? '0 0 0 3px rgb(var(--s800)), 0 0 0 6px rgb(var(--lima))' : '';
        });
    }
    function aplicar(tema) {
        if (tema === 'quizify') delete raiz.dataset.tema; else raiz.dataset.tema = tema;
        try { localStorage.setItem(CHAVE, tema); } catch { /* sem armazenamento: vale só nesta página */ }
        if (barra && window.CORES_BARRA) barra.content = window.CORES_BARRA[tema];
        marcar();
    }
    const fechar = () => folha.classList.add('hidden');

    abrir.addEventListener('click', () => { marcar(); folha.classList.remove('hidden'); });
    folha.addEventListener('click', (e) => {
        const botao = e.target.closest('button[data-tema]');
        if (botao) { aplicar(botao.dataset.tema); setTimeout(fechar, 250); }
        else if (e.target.closest('[data-fechar]')) fechar();
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fechar(); });
})();
