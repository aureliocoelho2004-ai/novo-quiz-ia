<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Quizify - Gerador de Quizzes e Flashcards com IA</title>
    <!-- Tailwind CSS para um design moderno e responsivo -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Biblioteca de Confetes para o efeito de 100% de acertos -->
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
</head>
<body class="bg-slate-900 text-slate-100 min-h-screen flex flex-col items-center justify-between p-4">

    <div class="w-full max-w-md bg-slate-800 rounded-2xl shadow-xl p-6 border border-slate-700">
        <!-- Cabeçalho -->
        <div class="text-center mb-6">
            <h1 class="text-3xl font-extrabold text-red-500 tracking-wide">🎲 Quizify</h1>
            <p class="text-sm text-slate-400 mt-1">Transforme documentos em quizzes interativos com IA</p>
        </div>

        <!-- Seção de Upload / Configuração -->
        <div id="setup-section" class="space-y-4">
            <div>
                <label class="block text-sm font-medium mb-2 text-slate-300">Carregar Arquivos ou Fotos (Máx. 5):</label>
                <input type="file" id="imageInput" accept=".pdf,.docx,.pptx,image/*" multiple onchange="atualizarContadorArquivos()"
                    class="w-full text-sm text-slate-400 file:mr-4 file:py-2 file:px-4 file:rounded-xl file:border-0 file:text-sm file:font-semibold file:bg-red-500 file:text-white hover:file:bg-red-600 cursor-pointer">
                <!-- Contador Visual de Arquivos -->
                <p id="file-counter-text" class="text-xs text-slate-400 mt-2">Nenhum arquivo selecionado (0/5)</p>
            </div>

            <div>
                <label class="block text-sm font-medium mb-2 text-slate-300">Número de Perguntas (5 a 50):</label>
                <input type="number" id="numQuestions" min="5" max="50" value="10" 
                    class="w-full bg-slate-900 border border-slate-700 rounded-xl p-3 text-white focus:outline-none focus:border-red-500">
            </div>

            <button onclick="gerarQuiz()" class="w-full bg-red-500 hover:bg-red-600 font-bold py-3 rounded-xl transition duration-200 shadow-lg shadow-red-500/30">
                Gerar Quiz com IA 🚀
            </button>
        </div>

        <!-- Seção do Quiz (Oculta inicialmente) -->
        <div id="quiz-section" class="hidden space-y-4">
            <div class="flex justify-between text-xs text-slate-400 mb-2">
                <span id="question-progress">Pergunta 1 de 10</span>
                <span id="score-counter">Acertos: 0</span>
            </div>
            
            <div id="question-container" class="bg-slate-900 p-4 rounded-xl border border-slate-700">
                <!-- A pergunta será injetada aqui -->
            </div>

            <div id="options-container" class="space-y-2">
                <!-- As opções serão injetadas aqui -->
            </div>

            <div id="feedback-container" class="text-sm font-medium mt-2"></div>
        </div>

        <!-- Seção de Conclusão / Resultados -->
        <div id="result-section" class="hidden text-center space-y-4">
            <h2 class="text-2xl font-bold text-green-400">Quiz Concluído! 🎉</h2>
            <p id="final-score-text" class="text-slate-300"></p>
            
            <div class="space-y-2">
                <button onclick="reiniciarQuizCompleto()" class="w-full bg-blue-600 hover:bg-blue-700 font-bold py-3 rounded-xl transition">
                    Refazer Tudo 🔄
                </button>
                <button id="btn-retry-errors" onclick="refazerErros()" class="w-full bg-amber-600 hover:bg-amber-700 font-bold py-3 rounded-xl transition hidden">
                    Refazer Apenas as Erradas 🎯
                </button>
            </div>
        </div>
    </div>

    <!-- Rodapé -->
    <footer class="text-xs text-slate-500 mt-6">
        Quizify &copy; 2026 - Todos os direitos reservados.
    </footer>

    <script>
        let questoes = [];
        let indiceAtual = 0;
        let acertos = 0;
        let questoesErradas = [];
        let modoErradas = false;

        // Atualiza o contador visual e valida o limite de 5 arquivos
        function atualizarContadorArquivos() {
            const input = document.getElementById('imageInput');
            const counterText = document.getElementById('file-counter-text');
            const totalFiles = input.files.length;

            if (totalFiles > 5) {
                counterText.innerHTML = `<span class="text-red-400 font-semibold">⚠️ Selecionou ${totalFiles} arquivos. O limite máximo é 5!</span>`;
                input.value = ""; // Limpa a seleção se passar do limite
            } else if (totalFiles > 0) {
                counterText.innerHTML = `<span class="text-green-400">✅ ${totalFiles} de 5 arquivos selecionados.</span>`;
            } else {
                counterText.innerText = "Nenhum arquivo selecionado (0/5)";
            }
        }

        // Função para comprimir a imagem antes de enviar (reduz o tamanho e evita sobrecarga)
        function comprimirImagem(file) {
            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.readAsDataURL(file);
                reader.onload = (event) => {
                    const img = new Image();
                    img.src = event.target.result;
                    img.onload = () => {
                        const canvas = document.createElement('canvas');
                        let width = img.width;
                        let height = img.height;

                        const MAX_SIZE = 1200;
                        if (width > height && width > MAX_SIZE) {
                            height *= MAX_SIZE / width;
                            width = MAX_SIZE;
                        } else if (height > MAX_SIZE) {
                            width *= MAX_SIZE / height;
                            height = MAX_SIZE;
                        }

                        canvas.width = width;
                        canvas.height = height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, width, height);

                        const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
                        resolve(dataUrl);
                    }
                }
            });
        }

        async function gerarQuiz() {
            const input = document.getElementById('imageInput');
            
            if (input.files.length === 0) {
                alert("Por favor, selecione pelo menos um arquivo ou foto.");
                return;
            }

            if (input.files.length > 5) {
                alert("Pode carregar no máximo 5 arquivos de cada vez.");
                return;
            }

            const imagensProcessadas = [];
            for (let i = 0; i < input.files.length; i++) {
                const file = input.files[i];
                if (file.type.startsWith('image/')) {
                    const imgComprimida = await comprimirImagem(file);
                    imagensProcessadas.push(imgComprimida);
                } else {
                    imagensProcessadas.push(file);
                }
            }

            const qtd = parseInt(document.getElementById('numQuestions').value) || 10;
            
            questoes = [];
            for (let i = 1; i <= qtd; i++) {
                questoes.push({
                    id: i,
                    pergunta: `Questão ${i}: Baseado nos arquivos enviados, qual é a resposta correta?`,
                    opcoes: [
                        "Resposta gerada pela IA com base nos documentos",
                        "Opção incorreta A",
                        "Opção incorreta B",
                        "Opção incorreta C"
                    ],
                    correta: 0
                });
            }

            indiceAtual = 0;
            acertos = 0;
            questoesErradas = [];
            modoErradas = false;

            document.getElementById('setup-section').classList.add('hidden');
            document.getElementById('quiz-section').classList.remove('hidden');
            carregarPergunta();
        }

        function carregarPergunta() {
            const listaAtiva = modoErradas ? questoesErradas : questoes;
            if (indiceAtual >= listaAtiva.length) {
                finalizarQuiz();
                return;
            }

            const q = listaAtiva[indiceAtual];
            document.getElementById('question-progress').innerText = `Pergunta ${indiceAtual + 1} de ${listaAtiva.length}`;
            document.getElementById('score-counter').innerText = `Acertos: ${acertos}`;
            document.getElementById('question-container').innerText = q.pergunta;
            document.getElementById('feedback-container').innerText = '';

            const optionsContainer = document.getElementById('options-container');
            optionsContainer.innerHTML = '';

            q.opcoes.forEach((opcao, index) => {
                const btn = document.createElement('button');
                btn.className = "w-full text-left bg-slate-800 hover:bg-slate-700 border border-slate-700 p-3 rounded-xl transition text-sm";
                btn.innerText = opcao;
                btn.onclick = () => verificarResposta(index, q);
                optionsContainer.appendChild(btn);
            });
        }

        function verificarResposta(indexSelecionado, q) {
            const feedback = document.getElementById('feedback-container');

            if (indexSelecionado === q.correta) {
                feedback.className = "text-sm font-medium mt-2 text-green-400";
                feedback.innerText = "Resposta Correta! 🎯";
                acertos++;
            } else {
                feedback.className = "text-sm font-medium mt-2 text-red-400";
                feedback.innerText = "Resposta Incorreta. Vamos rever esta depois!";
                if (!questoesErradas.some(item => item.id === q.id)) {
                    questoesErradas.push(q);
                }
            }

            setTimeout(() => {
                indiceAtual++;
                carregarPergunta();
            }, 1200);
        }

        function finalizarQuiz() {
            document.getElementById('quiz-section').classList.add('hidden');
            document.getElementById('result-section').classList.remove('hidden');

            const totalOriginal = questoes.length;
            document.getElementById('final-score-text').innerText = `Você acertou ${acertos} de ${totalOriginal} questões no total.`;

            const btnRetryErros = document.getElementById('btn-retry-errors');

            // Disparar palmas (confetes) APENAS se atingir 100% de acertos
            if (acertos === totalOriginal) {
                dispararPalmasEfeitos();
                btnRetryErros.classList.add('hidden');
            } else {
                if (questoesErradas.length > 0) {
                    btnRetryErros.classList.remove('hidden');
                }
            }
        }

        function dispararPalmasEfeitos() {
            confetti({
                particleCount: 150,
                spread: 80,
                origin: { y: 0.6 }
            });
        }

        function reiniciarQuizCompleto() {
            document.getElementById('result-section').classList.add('hidden');
            document.getElementById('setup-section').classList.remove('hidden');
            document.getElementById('imageInput').value = "";
            document.getElementById('file-counter-text').innerText = "Nenhum arquivo selecionado (0/5)";
        }

        function refazerErros() {
            if (questoesErradas.length === 0) return;
            questoes = [...questoesErradas];
            questoesErradas = [];
            indiceAtual = 0;
            modoErradas = true;

            document.getElementById('result-section').classList.add('hidden');
            document.getElementById('quiz-section').classList.remove('hidden');
            carregarPergunta();
        }
    </script>
</body>
</html>
