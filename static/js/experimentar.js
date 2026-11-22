// Quiz antes do cadastro: gera sem conta, mostra 3 questões e pede a conta para salvar.
(() => {
    const raiz = document.getElementById('experimentar');
    if (!raiz) return;
    const publico = raiz.dataset.publico;
    const palavra = raiz.dataset.palavra;
    const nomeItens = raiz.dataset.itens;
    const COTA = Number(raiz.dataset.cota) || 5;
    const MAX_ARQUIVOS = Number(raiz.dataset.maxArquivos);
    const MAX_IMAGENS = Number(raiz.dataset.maxImagens) || 10;
    const ehFoto = (f) => (f.type || '').startsWith('image/') || /\.(jpe?g|png|webp|heic|heif)$/i.test(f.name || '');
    const limiteDe = (lista) => (lista.length && [...lista].every(ehFoto) ? MAX_IMAGENS : MAX_ARQUIVOS);
    const MAX_BYTES = Number(raiz.dataset.maxMb) * 1024 * 1024;
    const erro = document.getElementById('erro');
    const etapas = ['escolher', 'processando', 'previa', 'conta'];

    function mostrar(...visiveis) {
        etapas.forEach((e) => document.getElementById(`etapa-${e}`).classList.toggle('hidden', !visiveis.includes(e)));
    }

    function falhar(texto, cadastrar) {
        mostrar('escolher');
        erro.textContent = `❌ ${texto}`;
        if (cadastrar) {
            erro.insertAdjacentHTML('beforeend', ` <a href="/cadastro?teste=1&p=${publico}" class="underline font-bold">Criar conta grátis</a>`);
        }
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

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

    function el(tag, classe, texto) {
        const n = document.createElement(tag);
        if (classe) n.className = classe;
        if (texto !== undefined) n.textContent = texto;
        return n;
    }

    function pedirConta(json) {
        const resto = Math.max(0, json.total - json.previa.length);
        document.getElementById('titulo-conta').textContent = resto
            ? `Gostou? Salve o ${palavra} e veja as outras ${resto} ${nomeItens}`
            : `Gostou? Salve o seu ${palavra}`;
        document.getElementById('sub-conta').textContent = json.exemplo
            ? `Conta grátis, sem cartão. Você ganha ${COTA} quizzes para criar com o seu material.`
            : `Conta grátis, sem cartão. Você ganha mais ${COTA - 1} quizzes.`;
        mostrar('previa', 'conta');
        setTimeout(() => document.getElementById('etapa-conta').scrollIntoView({ behavior: 'smooth', block: 'start' }), 300);
    }

    function mostrarPrevia(json) {
        if (window.fbq) { try { window.fbq('trackCustom', 'QuizGerado', { publico, exemplo: !!json.exemplo }); } catch (_) {} }
        document.getElementById('titulo-previa').textContent = `Seu ${palavra} está pronto: ${json.total} ${nomeItens}`;
        const area = document.getElementById('questoes');
        area.innerHTML = '';
        let respondidas = 0;
        json.previa.forEach((q, n) => {
            const card = el('div', 'bg-slate-900 border border-slate-700 rounded-2xl p-4 space-y-3');
            card.appendChild(el('p', 'text-xs text-slate-400', `${n + 1} de ${json.total}`));
            card.appendChild(el('p', 'font-semibold', q.pergunta));
            const opcoes = el('div', 'space-y-2');
            const explicacao = el('p', 'hidden text-sm rounded-xl p-3');
            q.opcoes.forEach((texto, i) => {
                const b = el('button', 'w-full text-left border border-slate-600 rounded-xl px-3 py-2.5 text-sm hover:border-lima', texto);
                b.type = 'button';
                b.addEventListener('click', () => {
                    if (card.dataset.ok) return;
                    card.dataset.ok = '1';
                    [...opcoes.children].forEach((x, j) => {
                        x.disabled = true;
                        if (j === q.correta) x.classList.add('border-green-500', 'bg-green-900/40');
                    });
                    const certo = i === q.correta;
                    if (!certo) b.classList.add('border-red-500', 'bg-red-900/40');
                    explicacao.textContent = `${certo ? '✅ Certo!' : '❌ Quase!'} ${q.explicacao || ''}`.trim();
                    explicacao.classList.remove('hidden');
                    explicacao.classList.add(certo ? 'bg-green-900/30' : 'bg-slate-800');
                    respondidas += 1;
                    if (respondidas === json.previa.length) pedirConta(json);
                });
                opcoes.appendChild(b);
            });
            card.appendChild(opcoes);
            card.appendChild(explicacao);
            area.appendChild(card);
        });
        const pular = el('button', 'w-full text-sm text-slate-400 underline', `Salvar e ver todas as ${nomeItens}`);
        pular.type = 'button';
        pular.addEventListener('click', () => pedirConta(json));
        area.appendChild(pular);
        mostrar('previa');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    async function pedir(dados) {
        mostrar('processando');
        erro.textContent = '';
        try {
            dados.append('p', publico);
            const resposta = await fetch('/api/experimentar', { method: 'POST', body: dados });
            const json = await resposta.json().catch(() => ({}));
            if (!resposta.ok) return falhar(json.erro || `Erro no servidor (${resposta.status}).`, json.cadastrar);
            mostrarPrevia(json);
        } catch (e) {
            falhar(e.message || 'Não foi possível enviar. Verifique a internet e tente de novo.');
        }
    }

    async function enviar(files) {
        const lista = [...files];
        if (!lista.length) return;
        if (lista.length > limiteDe(lista)) return falhar(`Envie no máximo ${MAX_ARQUIVOS} arquivos, ou até ${MAX_IMAGENS} fotos.`);
        mostrar('processando');
        const processados = await Promise.all(lista.map(comprimir));
        if (processados.reduce((s, f) => s + f.size, 0) > MAX_BYTES) return falhar(`O tamanho total excede ${raiz.dataset.maxMb} MB.`);
        const dados = new FormData();
        processados.forEach((f) => dados.append('arquivos', f, f.name));
        pedir(dados);
    }

    document.getElementById('form-tema').addEventListener('submit', (e) => {
        e.preventDefault();
        const tema = document.getElementById('campo-tema').value.trim();
        if (tema.length < 3) return falhar('Digite um tema com pelo menos 3 letras.');
        const dados = new FormData();
        dados.append('tema', tema);
        pedir(dados);
    });
    document.getElementById('campo-camera').addEventListener('change', (e) => enviar(e.target.files));
    document.getElementById('campo-arquivo').addEventListener('change', (e) => enviar(e.target.files));
    document.getElementById('btn-exemplo').addEventListener('click', () => {
        const dados = new FormData();
        dados.append('exemplo', '1');
        pedir(dados);
    });
})();
