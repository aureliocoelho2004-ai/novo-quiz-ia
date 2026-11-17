// Tela pós-cadastro: uma única ação, criar o primeiro quiz.
(() => {
    const raiz = document.getElementById('comecar');
    if (!raiz) return;
    const publico = raiz.dataset.publico;
    const MAX_ARQUIVOS = Number(raiz.dataset.maxArquivos);
    const MAX_BYTES = Number(raiz.dataset.maxMb) * 1024 * 1024;
    let restam = raiz.dataset.restam === '' ? null : Number(raiz.dataset.restam);
    const etapas = ['escolher', 'processando', 'pronto'];
    const erro = document.getElementById('erro');
    const palavra = publico === 'pais' ? 'quiz' : 'simulado';
    const itens = publico === 'pais' ? 'perguntas' : 'questões';

    function mostrar(etapa) {
        etapas.forEach((e) => document.getElementById(`etapa-${e}`).classList.toggle('hidden', e !== etapa));
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function falhar(texto, linkPlanos) {
        mostrar('escolher');
        erro.textContent = `❌ ${texto}`;
        if (linkPlanos) erro.insertAdjacentHTML('beforeend', ` <a href="${linkPlanos}" class="underline font-bold">Ver planos</a>`);
    }

    // Reduz fotos grandes no próprio celular antes de enviar (mais rápido no 4G)
    function comprimir(file) {
        if (!file.type.startsWith('image/')) return Promise.resolve(file);
        return new Promise((resolve) => {
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => {
                const escala = Math.min(1, 1200 / Math.max(img.width, img.height));
                const canvas = document.createElement('canvas');
                canvas.width = Math.round(img.width * escala);
                canvas.height = Math.round(img.height * escala);
                canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                URL.revokeObjectURL(url);
                canvas.toBlob((blob) => {
                    if (!blob || blob.size >= file.size) return resolve(file);
                    resolve(new File([blob], file.name.replace(/\.[^.]+$/, '') + '.jpg', { type: 'image/jpeg' }));
                }, 'image/jpeg', 0.8);
            };
            img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
            img.src = url;
        });
    }

    function pronto(json) {
        const exemplo = !!json.exemplo;
        document.getElementById('titulo-pronto').textContent = exemplo
            ? `Seu ${palavra} de exemplo está pronto: ${json.total} ${itens}`
            : `Seu ${palavra} está pronto: ${json.total} ${itens}`;
        document.getElementById('btn-comecar').href = json.link;
        const filho = document.getElementById('btn-filho');
        if (filho) {
            const texto = `Oi! Fiz um quiz para você treinar para a prova. Responde aqui: ${json.link}`;
            filho.href = `https://wa.me/?text=${encodeURIComponent(texto)}`;
        }
        if (!exemplo && restam !== null) restam = Math.max(0, restam - 1);
        const aviso = document.getElementById('aviso-restam');
        if (restam === null) aviso.textContent = '';
        else if (exemplo) aviso.textContent = `O exemplo não gastou nada: você ainda tem ${restam} quizzes grátis para criar com o seu material.`;
        else aviso.textContent = restam > 0 ? `Você ainda tem ${restam} quiz${restam > 1 ? 'zes' : ''} grátis.` : 'Você usou todos os quizzes grátis.';
        mostrar('pronto');
    }

    async function enviar(files) {
        erro.textContent = '';
        const lista = [...files];
        if (!lista.length) return;
        if (lista.length > MAX_ARQUIVOS) return falhar(`Envie no máximo ${MAX_ARQUIVOS} arquivos.`);
        mostrar('processando');
        try {
            const processados = await Promise.all(lista.map(comprimir));
            if (processados.reduce((s, f) => s + f.size, 0) > MAX_BYTES) throw new Error(`O tamanho total excede ${raiz.dataset.maxMb} MB.`);
            const dados = new FormData();
            dados.append('tipo', 'quiz');
            dados.append('quantidade', '10');
            dados.append('titulo', raiz.dataset.titulo);
            dados.append('divulgar', '1');
            processados.forEach((f) => dados.append('arquivos', f, f.name));
            const resposta = await fetch('/api/gerar', { method: 'POST', body: dados });
            if (resposta.status === 401) { window.location.href = '/login'; return; }
            const json = await resposta.json().catch(() => ({}));
            if (!resposta.ok) return falhar(json.erro || `Erro no servidor (${resposta.status}).`, json.assinar);
            pronto(json);
        } catch (e) {
            falhar(e.message || 'Não foi possível enviar. Verifique a internet e tente de novo.');
        }
    }

    document.getElementById('campo-camera').addEventListener('change', (e) => enviar(e.target.files));
    document.getElementById('campo-arquivo').addEventListener('change', (e) => enviar(e.target.files));

    document.getElementById('btn-exemplo').addEventListener('click', async () => {
        erro.textContent = '';
        mostrar('processando');
        try {
            const dados = new FormData();
            dados.append('p', publico);
            const resposta = await fetch('/api/exemplo', { method: 'POST', body: dados });
            if (resposta.status === 401) { window.location.href = '/login'; return; }
            const json = await resposta.json().catch(() => ({}));
            if (!resposta.ok) return falhar(json.erro || 'Não foi possível abrir o exemplo agora.');
            pronto(json);
        } catch (e) {
            falhar('Não foi possível abrir o exemplo. Verifique a internet e tente de novo.');
        }
    });

    document.getElementById('btn-outro').addEventListener('click', () => {
        document.getElementById('campo-camera').value = '';
        document.getElementById('campo-arquivo').value = '';
        mostrar('escolher');
    });
})();
