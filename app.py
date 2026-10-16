import streamlit as st
import google.generativeai as genai
import PyPDF2
import docx
import json
import re

# ==========================================
# CONFIGURAÇÃO DA IA
# ==========================================
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
modelo = genai.GenerativeModel("gemini-3.5-flash")
def extrair_texto_pdf(arquivo):
    leitor = PyPDF2.PdfReader(arquivo)
    texto = ""
    for pagina in leitor.pages:
        texto += pagina.extract_text() + "\n"
    return texto

def extrair_texto_docx(arquivo):
    doc = docx.Document(arquivo)
    texto = "\n".join([paragrafo.text for paragrafo in doc.paragraphs])
    return texto

# Recebe agora o número de perguntas escolhido pelo utilizador
def gerar_quiz_da_ia(texto_base, num_perguntas):
    prompt = f"""
    Baseado no texto abaixo, crie um quiz de múltipla escolha com exatas {num_perguntas} perguntas.
    Retorne APENAS um array JSON válido, sem formatação markdown, com a seguinte estrutura:
    [
      {{
        "pergunta": "Sua pergunta aqui?",
        "opcoes": ["Opcao A", "Opcao B", "Opcao C", "Opcao D"],
        "resposta_correta": 1,
        "explicacao": "Explicação curta do porquê esta é a resposta correta e as outras não."
      }}
    ]
    A resposta_correta deve ser o índice (0 a 3) da opção certa.
    
    TEXTO BASE:
    {texto_base[:15000]}
    """
    resposta = modelo.generate_content(prompt)
    texto_resposta = re.sub(r'```json\n?', '', resposta.text)
    texto_resposta = re.sub(r'```\n?', '', texto_resposta)
    return json.loads(texto_resposta.strip())

def obter_html_jogo(json_perguntas):
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-PT">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Quiz Interativo</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
            body {{ font-family: 'Poppins', sans-serif; }}
            .btn-opcao {{ transition: all 0.2s; }}
            .btn-opcao:hover:not(:disabled) {{ transform: scale(1.02); }}
            .correto {{ background-color: #22c55e !important; color: white !important; border-color: #22c55e !important; }}
            .errado {{ background-color: #ef4444 !important; color: white !important; border-color: #ef4444 !important; }}
        </style>
    </head>
    <body class="bg-slate-900 text-white flex items-center justify-center min-h-screen p-4">
        <div class="w-full max-w-md bg-slate-800 rounded-2xl shadow-2xl p-6 border border-slate-700">
            
            <div class="flex justify-between items-center mb-6">
                <div class="text-sm font-semibold text-slate-400">Questão <span id="num-questao">1</span>/<span id="total-questoes"></span></div>
                <div class="text-sm font-semibold text-indigo-400">Pontos: <span id="pontuacao">0</span></div>
            </div>
            
            <div class="w-full bg-slate-700 rounded-full h-2.5 mb-6">
                <div id="barra-progresso" class="bg-indigo-500 h-2.5 rounded-full transition-all duration-500" style="width: 0%"></div>
            </div>
            
            <div id="tela-pergunta">
                <h2 id="texto-pergunta" class="text-xl font-bold mb-6 text-center text-slate-100">Carregando...</h2>
                <div id="opcoes-container" class="flex flex-col gap-3"></div>
                
                <!-- Área de Feedback (Invisível no início) -->
                <div id="tela-feedback" class="hidden mt-6 p-4 rounded-xl text-center">
                    <h3 id="feedback-titulo" class="font-bold text-lg mb-2"></h3>
                    <p id="feedback-texto" class="text-sm text-slate-200"></p>
                    <button onclick="proximaPergunta()" class="mt-4 w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-4 rounded-xl transition-all shadow-lg">Continuar</button>
                </div>
            </div>
            
            <div id="tela-resultado" class="hidden text-center">
                <div class="text-6xl mb-4">🏆</div>
                <h2 class="text-2xl font-bold mb-2">Fim de Jogo!</h2>
                <p class="text-slate-300 mb-6">Fez <span id="pontuacao-final" class="font-bold text-indigo-400 text-xl"></span> pontos.</p>
                <button onclick="location.reload()" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-4 rounded-xl transition-all">Jogar Novamente</button>
            </div>
        </div>

        <script>
            const perguntas = {json.dumps(json_perguntas)};
            let indiceAtual = 0; let pontos = 0; let respondido = false;
            document.getElementById('total-questoes').innerText = perguntas.length;

            function carregarPergunta() {{
                respondido = false;
                const p = perguntas[indiceAtual];
                document.getElementById('texto-pergunta').innerText = p.pergunta;
                document.getElementById('num-questao').innerText = indiceAtual + 1;
                document.getElementById('barra-progresso').style.width = ((indiceAtual / perguntas.length) * 100) + '%';
                
                document.getElementById('tela-feedback').classList.add('hidden');
                
                const container = document.getElementById('opcoes-container');
                container.innerHTML = '';
                
                p.opcoes.forEach((opcao, index) => {{
                    const btn = document.createElement('button');
                    btn.innerText = opcao;
                    btn.className = 'btn-opcao w-full bg-slate-700 border-2 border-slate-600 text-left py-3 px-5 rounded-xl font-semibold text-slate-200 hover:bg-slate-600 hover:border-indigo-400';
                    btn.onclick = () => verificarResposta(index, btn);
                    container.appendChild(btn);
                }});
            }}

            function verificarResposta(indiceSelecionado, botaoClicado) {{
                if (respondido) return;
                respondido = true;
                
                // Desativar botões
                const botoes = document.querySelectorAll('.btn-opcao');
                botoes.forEach(b => b.disabled = true);
                
                const p = perguntas[indiceAtual];
                const telaFeedback = document.getElementById('tela-feedback');
                const feedbackTitulo = document.getElementById('feedback-titulo');
                const feedbackTexto = document.getElementById('feedback-texto');
                
                telaFeedback.classList.remove('hidden');

                if (indiceSelecionado === p.resposta_correta) {{
                    botaoClicado.classList.add('correto'); 
                    pontos += 100;
                    document.getElementById('pontuacao').innerText = pontos;
                    
                    telaFeedback.className = 'mt-6 p-4 rounded-xl text-center bg-green-900/40 border border-green-500 block';
                    feedbackTitulo.innerText = '✅ Correto!';
                    feedbackTitulo.className = 'font-bold text-lg mb-2 text-green-400';
                    feedbackTexto.innerText = p.explicacao;
                }} else {{
                    botaoClicado.classList.add('errado');
                    botoes[p.resposta_correta].classList.add('correto');
                    
                    telaFeedback.className = 'mt-6 p-4 rounded-xl text-center bg-red-900/40 border border-red-500 block';
                    feedbackTitulo.innerText = '❌ Incorreto!';
                    feedbackTitulo.className = 'font-bold text-lg mb-2 text-red-400';
                    feedbackTexto.innerHTML = `A resposta certa era: <b>${{p.opcoes[p.resposta_correta]}}</b>.<br><br>${{p.explicacao}}`;
                }}
            }}

            function proximaPergunta() {{
                indiceAtual++;
                if (indiceAtual < perguntas.length) carregarPergunta();
                else mostrarResultado();
            }}

            function mostrarResultado() {{
                document.getElementById('tela-pergunta').classList.add('hidden');
                document.getElementById('barra-progresso').style.width = '100%';
                document.getElementById('tela-resultado').classList.remove('hidden');
                document.getElementById('pontuacao-final').innerText = pontos;
            }}
            carregarPergunta();
        </script>
    </body>
    </html>
    """
    return html

# ==========================================
# INTERFACE DO PROFESSOR (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Fábrica de Quizzes", layout="centered")
st.title("🎲 Fábrica de Quizzes")
st.write("Crie o jogo aqui e descarregue-o para enviar aos alunos!")

# Nova opção: Escolher a quantidade de perguntas
qnt_perguntas = st.number_input("Quantas perguntas quer gerar no jogo?", min_value=1, max_value=20, value=5)

arquivo_enviado = st.file_uploader("Envie o seu material de estudo (PDF ou Word)", type=["pdf", "docx"])

if arquivo_enviado is not None:
    if st.button("✨ Gerar Jogo", use_container_width=True):
        with st.spinner("A IA está a estudar o seu documento e a criar as perguntas com explicações..."):
            try:
                if arquivo_enviado.name.endswith(".pdf"):
                    texto_extraido = extrair_texto_pdf(arquivo_enviado)
                elif arquivo_enviado.name.endswith(".docx"):
                    texto_extraido = extrair_texto_docx(arquivo_enviado)
                
                perguntas_json = gerar_quiz_da_ia(texto_extraido, qnt_perguntas)
                html_final = obter_html_jogo(perguntas_json)
                
                st.success("✅ Jogo criado com sucesso!")
                
                # NOVIDADE: Em vez de mostrar o jogo aqui, cria um botão para descarregar
                st.download_button(
                    label="📥 Descarregar Ficheiro do Jogo para os Alunos",
                    data=html_final,
                    file_name="meu_quiz_gamificado.html",
                    mime="text/html",
                    use_container_width=True
                )
                
                st.info("💡 **Dica:** Pode enviar este ficheiro diretamente por WhatsApp ou Email aos alunos (ele abre no navegador do telemóvel).")
                
            except Exception as e:
                st.error(f"Ocorreu um erro: {e}")
