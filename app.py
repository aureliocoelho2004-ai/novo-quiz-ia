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
# Mantido o modelo 3.5 Flash conforme validado nos seus testes
modelo = genai.GenerativeModel("gemini-3.5-flash")

# ==========================================
# CONTROLO DE ACESSO / USUÁRIOS DE DEMO
# ==========================================
USUARIOS_AUTORIZADOS = {
    "admin": "admin123",           
    "escola_demo": "quiz2026",     
    "professor": "aula123"         
}

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_atual"] = ""

def tela_login():
    st.markdown("<h2 style='text-align: center;'>🔐 Acesso Restrito - Quizify</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Insira as suas credenciais para aceder à plataforma.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            usuario = st.text_input("Utilizador / E-mail")
            senha = st.text_input("Palavra-passe", type="password")
            botao_entrar = st.form_submit_button("Entrar na Plataforma", use_container_width=True)
            
            if botao_entrar:
                if usuario in USUARIOS_AUTORIZADOS and USUARIOS_AUTORIZADOS[usuario] == senha:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_atual"] = usuario
                    st.rerun()
                else:
                    st.error("Utilizador ou palavra-passe incorretos.")

def logout():
    st.session_state["autenticado"] = False
    st.session_state["usuario_atual"] = ""
    st.rerun()

# ==========================================
# FUNÇÕES DE PROCESSAMENTO
# ==========================================
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

def obter_html_jogo(json_perguntas, titulo_quiz, nome_professor):
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-PT">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{titulo_quiz}</title>
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
        
        <audio id="som-palmas" src="https://actions.google.com/sounds/v1/crowds/light_applause.ogg"></audio>

        <div class="w-full max-w-md bg-slate-800 rounded-2xl shadow-2xl p-6 border border-slate-700">
            
            <!-- Título Persistente e Nome do Professor -->
            <h1 class="text-2xl font-extrabold text-center text-indigo-400 mb-1">{titulo_quiz}</h1>
            <p class="text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700">Prof. {nome_professor}</p>
            
            <div class="flex justify-between items-center mb-6">
                <div class="text-sm font-semibold text-slate-400">Questão <span id="num-questao">1</span>/<span id="total-questoes"></span></div>
                <div class="text-sm font-semibold text-indigo-400">Desempenho: <span id="pontuacao">0%</span></div>
            </div>
            
            <div class="w-full bg-slate-700 rounded-full h-2.5 mb-6">
                <div id="barra-progresso" class="bg-indigo-500 h-2.5 rounded-full transition-all duration-500" style="width: 0%"></div>
            </div>
            
            <div id="tela-pergunta">
                <h2 id="texto-pergunta" class="text-xl font-bold mb-6 text-center text-slate-100">A carregar...</h2>
                <div id="opcoes-container" class="flex flex-col gap-3"></div>
                
                <div id="tela-feedback" class="hidden mt-6 p-4 rounded-xl text-center">
                    <h3 id="feedback-titulo" class="font-bold text-lg mb-2"></h3>
                    <p id="feedback-texto" class="text-sm text-slate-200"></p>
                    <button onclick="proximaPergunta()" class="mt-4 w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-4 rounded-xl transition-all shadow-lg">Continuar</button>
                </div>
            </div>
            
            <div id="tela-resultado" class="hidden text-center">
                <div class="text-6xl mb-4">🏆</div>
                <h2 class="text-2xl font-bold mb-2">Fim de Jogo!</h2>
                <p class="text-slate-300 mb-6">Acertou <span id="pontuacao-final" class="font-bold text-indigo-400 text-2xl"></span> do quiz.</p>
                <button onclick="location.reload()" class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-3 px-4 rounded-xl transition-all">Jogar Novamente</button>
            </div>
        </div>

        <script>
            const perguntas = {json.dumps(json_perguntas)};
            let indiceAtual = 0; 
            let acertos = 0; 
            let respondido = false;
            
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
                
                const botoes = document.querySelectorAll('.btn-opcao');
                botoes.forEach(b => b.disabled = true);
                
                const p = perguntas[indiceAtual];
                const telaFeedback = document.getElementById('tela-feedback');
                const feedbackTitulo = document.getElementById('feedback-titulo');
                const feedbackTexto = document.getElementById('feedback-texto');
                
                telaFeedback.classList.remove('hidden');

                if (indiceSelecionado === p.resposta_correta) {{
                    botaoClicado.classList.add('correto'); 
                    acertos++;
                    
                    const percentualAtual = Math.round((acertos / perguntas.length) * 100);
                    document.getElementById('pontuacao').innerText = percentualAtual + '%';
                    
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
                document.getElementById('som-palmas').play();
                document.getElementById('tela-pergunta').classList.add('hidden');
                document.getElementById('barra-progresso').style.width = '100%';
                document.getElementById('tela-resultado').classList.remove('hidden');
                
                const percentualFinal = Math.round((acertos / perguntas.length) * 100);
                document.getElementById('pontuacao-final').innerText = percentualFinal + '%';
            }}
            
            carregarPergunta();
        </script>
    </body>
    </html>
    """
    return html

# ==========================================
# CONTROLO DE FLUXO DA APLICAÇÃO
# ==========================================
st.set_page_config(page_title="Quizify", layout="centered")

if not st.session_state["autenticado"]:
    tela_login()
else:
    with st.sidebar:
        st.write(f"Conectado como: **{st.session_state['usuario_atual']}**")
        if st.button("Terminar Sessão", use_container_width=True):
            logout()
            
    st.title("🎲 Quizify")
    st.write("Transforme o seu material de estudo num jogo interativo em segundos!")

    # Novos inputs para personalização
    titulo_quiz = st.text_input("Qual é o título do Quiz?", value="Desafio de Conhecimento")
    nome_professor = st.text_input("Nome do Professor(a)", value="", placeholder="Ex: Maria João")
    qnt_perguntas = st.number_input("Quantas perguntas quer gerar no jogo?", min_value=1, max_value=30, value=5)

    arquivo_enviado = st.file_uploader("Envie o seu material de estudo (PDF ou Word)", type=["pdf", "docx"])

    if arquivo_enviado is not None:
        if st.button("✨ Gerar Jogo", use_container_width=True):
            with st.spinner("A IA está a analisar o documento e a criar o jogo..."):
                try:
                    if arquivo_enviado.name.endswith(".pdf"):
                        texto_extraido = extrair_texto_pdf(arquivo_enviado)
                    elif arquivo_enviado.name.endswith(".docx"):
                        texto_extraido = extrair_texto_docx(arquivo_enviado)
                    
                    perguntas_json = gerar_quiz_da_ia(texto_extraido, qnt_perguntas)
                    html_final = obter_html_jogo(perguntas_json, titulo_quiz, nome_professor)
                    
                    st.success("✅ Jogo criado com sucesso!")
                    
                    nome_ficheiro = titulo_quiz.replace(" ", "_").lower() + ".html"
                    
                    st.download_button(
                        label="📥 Descarregar Ficheiro do Jogo para os Alunos",
                        data=html_final,
                        file_name=nome_ficheiro,
                        mime="text/html",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"Ocorreu um erro: {e}")
