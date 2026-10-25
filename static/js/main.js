(() => {
    const form = document.getElementById('form-gerar');
    const inputArquivos = document.getElementById('arquivos');
    const contador = document.getElementById('contador-arquivos');
    const status = document.getElementById('status');
    const btnGerar = document.getElementById('btn-gerar');
    const MAX_ARQUIVOS = Number(form.dataset.maxArquivos);
    const MAX_BYTES = Number(form.dataset.maxMb) * 1024 * 1024;
    const LADO_MAXIMO = 1200;
    const QUALIDADE_JPEG = 0.8;

    let resultado = null;

    function mostrarStatus(texto, cor = 'text-slate-300') {
        status.className = `text-sm text-center min-h-[1.25rem] ${cor}`;
        status.textContent = texto;
    }

    // Contador visual e validação do limite de arquivos
    inputArquivos.addEventListener('change', () => {
        const total = inputArquivos.files.length;
        contador.className = 'text-xs mt-2';
        if (total > MAX_ARQUIVOS) {
            contador.classList.add('text-red-400', 'font-semibold');
            contador.textContent = `⚠️ Selecionou ${total} arquivos. O limite máximo é ${MAX_ARQUIVOS}!`;
            inputArquivos.value = '';
        } else if (total > 0) {
            contador.classList.add('text-green-400');
            contador.textContent = `✅ ${total} de ${MAX_ARQUIVOS} arquivos selecionados.`;
        } else {
            contador.classList.add('text-slate-400');
            contador.textContent = `Nenhum arquivo selecionado (0/${MAX_ARQUIVOS})`;
        }
    });

    // Redimensiona e comprime a foto no navegador. Se o navegador não conseguir
    // ler o formato (ex.: HEIC fora do Safari), envia o original e o servidor trata.
    function comprimirImagem(file) {
        return new Promise((resolve) => {
            const url = URL.createObjectURL(file);
            const img = new Image();
            img.onload = () => {
                const escala = Math.min(1, LADO_MAXIMO / Math.max(img.width, img.height));
                const canvas = document.createElement('canvas');
                canvas.width = Math.round(img.width * escala);
                canvas.height = Math.round(img.height * escala);
                canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
                URL.revokeObjectURL(url);
                canvas.toBlob((blob) => {
                    if (!blob || blob.size >= file.size) return resolve(file);
                    const nome = file.name.replace(/\.[^.]+$/, '') + '.jpg';
                    resolve(new File([blob], nome, { type: 'image/jpeg' }));
                }, 'image/jpeg', QUALIDADE_JPEG);
            };
            img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
            img.src = url;
        });
    }

    form.addEventListener('submit', async (evento) => {
        evento.preventDefault();
        const arquivos = [...inputArquivos.files];
        if (arquivos.length === 0) return mostrarStatus('Selecione pelo menos um arquivo ou foto.', 'text-red-400');
        if (arquivos.length > MAX_ARQUIVOS) return mostrarStatus(`Envie no máximo ${MAX_ARQUIVOS} arquivos.`, 'text-red-400');

        btnGerar.disabled = true;
        try {
            mostrarStatus('🗜️ Comprimindo imagens...');
            const processados = await Promise.all(
                arquivos.map((f) => (f.type.startsWith('image/') ? comprimirImagem(f) : f))
            );
            if (processados.reduce((s, f) => s + f.size, 0) > MAX_BYTES) {
                throw new Error(`O tamanho total excede ${form.dataset.maxMb} MB.`);
            }

            const dados = new FormData(form);
            processados.forEach((f) => dados.append('arquivos', f, f.name));

            mostrarStatus('🤖 A IA está lendo o material e criando o conteúdo... (pode levar até 1 minuto)');
            const resposta = await fetch('/api/gerar', { method: 'POST', body: dados });
            if (resposta.status === 401) {
                window.location.href = '/login';
                return;
            }
            const json = await resposta.json().catch(() => ({}));
            if (!resposta.ok) throw new Error(json.erro || `Erro no servidor (${resposta.status}).`);

            resultado = json;
            mostrarResultado();
        } catch (erro) {
            mostrarStatus(`❌ ${erro.message}`, 'text-red-400');
        } finally {
            btnGerar.disabled = false;
        }
    });

    function mostrarResultado() {
        const tipo = form.elements.tipo.value === 'quiz' ? 'perguntas' : 'flashcards';
        document.getElementById('resumo').textContent = `${resultado.total} ${tipo} gerados.`;
        document.getElementById('bloco-link').classList.toggle('hidden', !resultado.link);
        document.getElementById('aviso-link').classList.toggle('hidden', !!resultado.link);
        if (resultado.link) {
            document.getElementById('link').value = resultado.link;
            document.getElementById('btn-abrir').href = resultado.link;
        }
        document.getElementById('preview').srcdoc = resultado.html;
        form.classList.add('hidden');
        document.getElementById('resultado').classList.remove('hidden');
        mostrarStatus('');
    }

    document.getElementById('btn-copiar').addEventListener('click', async (e) => {
        const campo = document.getElementById('link');
        try {
            await navigator.clipboard.writeText(campo.value);
        } catch {
            campo.select();
            document.execCommand('copy');
        }
        e.target.textContent = 'Copiado!';
        setTimeout(() => { e.target.textContent = 'Copiar'; }, 1500);
    });

    // Download do HTML autônomo (funciona offline no Android/iOS/computador)
    document.getElementById('btn-baixar').addEventListener('click', () => {
        const blob = new Blob([resultado.html], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = Object.assign(document.createElement('a'), { href: url, download: resultado.nome_arquivo });
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    });

    document.getElementById('btn-novo').addEventListener('click', () => {
        resultado = null;
        document.getElementById('preview').srcdoc = '';
        document.getElementById('resultado').classList.add('hidden');
        form.classList.remove('hidden');
        inputArquivos.value = '';
        inputArquivos.dispatchEvent(new Event('change'));
    });
})();
