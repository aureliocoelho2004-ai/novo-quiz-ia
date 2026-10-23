import streamlit as st
import google.generativeai as genai
import streamlit.components.v1 as components
import PyPDF2
import docx
import pptx
from PIL import Image
import pytesseract
import json
import re
import time
import html

# ==========================================
# CONFIGURAÇÃO DA IA
# ==========================================
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    # Vamos manter o 1.5-flash aqui provisoriamente até vermos a lista
    modelo = genai.GenerativeModel("gemini-2.5-flash")
except Exception as e:
    st.error("Erro de configuração: Gemini API Key não encontrada nos Secrets.")
    st.stop()

# ==========================================
# CONFIGURAÇÃO DA PÁGINA E VISUAL
# ==========================================
st.set_page_config(page_title="Quizify", layout="centered")

esconder_menu = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """
st.markdown(esconder_menu, unsafe_allow_html=True)

# ==========================================
# CONTROLO DE ACESSO E SEGURANÇA (RATE LIMIT)
# ==========================================
USUARIOS_AUTORIZADOS = {
    "admin": "admin123",
    "escola_demo": "quiz2026",
    "professor": "aula123"
}

for i in range(1, 51):
    u = f"beta{i}"
    USUARIOS_AUTORIZADOS[u] = u

TAMANHO_MAXIMO_MB = 10
COOLDOWN_SEGUNDOS = 30
LIMITE_POR_SESSAO = 50

if "autenticado" not in st.session_state:
    st.session_state["autenticado"] = False
    st.session_state["usuario_atual"] = ""
if "ultimo_uso" not in st.session_state:
    st.session_state["ultimo_uso"] = 0.0
if "geracoes_nesta_sessao" not in st.session_state:
    st.session_state["geracoes_nesta_sessao"] = 0
if "quiz_html_pronto" not in st.session_state:
    st.session_state["quiz_html_pronto"] = None
if "flash_html_pronto" not in st.session_state:
    st.session_state["flash_html_pronto"] = None

def tela_login():
    st.markdown("<h2 style='text-align: center;'>🔐 Acesso Restrito - Quizify</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Insira as suas credenciais para aceder à plataforma.</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            usuario = st.text_input("Utilizador / E-mail").strip().lower()
            senha = st.text_input("Palavra-passe", type="password").strip()
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
    st.session_state["geracoes_nesta_sessao"] = 0
    st.session_state["quiz_html_pronto"] = None
    st.session_state["flash_html_pronto"] = None
    st.rerun()

def verificar_seguranca(arquivos):
    tamanho_total = sum([arq.size for arq in arquivos]) if isinstance(arquivos, list) else arquivos.size
    if tamanho_total > TAMANHO_MAXIMO_MB * 1024 * 1024:
        st.error(f"❌ Segurança: O tamanho total dos ficheiros excede o limite de {TAMANHO_MAXIMO_MB}MB.")
        return False
    if st.session_state["geracoes_nesta_sessao"] >= LIMITE_POR_SESSAO:
        st.error(f"⚠️ Já gerou {LIMITE_POR_SESSAO} conteúdos nesta sessão. Limite atingido.")
        return False
    tempo_decorrido = time.time() - st.session_state["ultimo_uso"]
    if tempo_decorrido < COOLDOWN_SEGUNDOS:
        st.warning(f"⏳ Aguarde {int(COOLDOWN_SEGUNDOS - tempo_decorrido)} segundos antes de gerar um novo conteúdo.")
        return False
    return True

# ==========================================
# EXTRAÇÃO DE TEXTO
# ==========================================
def extrair_texto_pdf(arquivo):
    try:
        arquivo.seek(0)
        leitor = PyPDF2.PdfReader(arquivo)
        texto = ""
        for idx, pagina in enumerate(leitor.pages):
            conteudo = pagina.extract_text()
            if conteudo:
                texto += conteudo + "\n"
        return texto
    except Exception as e:
        raise ValueError(f"Falha ao ler o PDF: {str(e)}")

def extrair_texto_docx(arquivo):
    try:
        arquivo.seek(0)
        doc = docx.Document(arquivo)
        trechos = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(trechos)
    except Exception as e:
        raise ValueError(f"O ficheiro Word está corrompido: {str(e)}")

def extrair_texto_pptx(arquivo):
    try:
        arquivo.seek(0)
        prs = pptx.Presentation(arquivo)
        trechos = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        if paragraph.text.strip():
                            trechos.append(paragraph.text.strip())
        return "\n".join(trechos)
    except Exception as e:
        raise ValueError(f"O ficheiro PowerPoint está corrompido: {str(e)}")

def extrair_texto_imagem(arquivo):
    try:
        arquivo.seek(0)
        imagem = Image.open(arquivo)
        imagem.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        imagem = imagem.convert('L')
        try:
            texto = pytesseract.image_to_string(imagem, lang='por')
        except Exception:
            texto = pytesseract.image_to_string(imagem)
        return texto
    except Exception as e:
        raise ValueError(f"Erro ao processar imagem: {str(e)}")

def processar_arquivo(arquivo):
    nome_arquivo = arquivo.name.lower()
    tipo_arquivo = getattr(arquivo, "type", "").lower()
    if nome_arquivo.endswith(".pdf") or tipo_arquivo == "application/pdf":
        return extrair_texto_pdf(arquivo)
    elif nome_arquivo.endswith(".docx") or "wordprocessingml" in tipo_arquivo:
        return extrair_texto_docx(arquivo)
    elif nome_arquivo.endswith(".pptx") or "presentationml" in tipo_arquivo:
        return extrair_texto_pptx(arquivo)
    elif nome_arquivo.endswith((".png", ".jpg", ".jpeg")) or tipo_arquivo.startswith("image/"):
        return extrair_texto_imagem(arquivo)
    else:
        raise ValueError("Formato não suportado.")

# ==========================================
# FUNÇÕES DO QUIZ & FLASHCARDS
# ==========================================
def gerar_quiz_da_ia(texto_base, num_perguntas):
    prompt = f"""
    Crie um quiz de múltipla escolha com exatas {num_perguntas} perguntas focadas no tema principal do texto.
    Retorne APENAS um array JSON válido:
    [
      {{
        "pergunta": "Sua pergunta aqui?",
        "opcoes": ["Opcao A", "Opcao B", "Opcao C", "Opcao D"],
        "resposta_correta": 1,
        "explicacao": "Explicação."
      }}
    ]
    --- TEXTO BASE ---
    {texto_base[:15000]}
    """
    resposta = modelo.generate_content(prompt)
    texto_resposta = re.sub(r'```json\n?', '', resposta.text)
    return json.loads(re.sub(r'```\n?', '', texto_resposta).strip())

def obter_html_jogo(json_perguntas, titulo_quiz, nome_professor):
    titulo_seguro = html.escape(titulo_quiz)
    nome_prof_seguro = html.escape(nome_professor)
    json_str = json.dumps(json_perguntas)

    html_export = """<!DOCTYPE html>
<html lang="pt-PT">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[[TITULO]]</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: sans-serif; }
        .btn-opcao { transition: all 0.2s; }
        .correto { background-color: #22c55e !important; color: white !important; }
        .errado { background-color: #ef4444 !important; color: white !important; }
    </style>
</head>
<body class="bg-slate-900 text-white flex items-center justify-center min-h-screen p-4">
    <div class="w-full max-w-md bg-slate-800 rounded-2xl p-6 border border-slate-700">
        <h1 class="text-2xl font-extrabold text-center text-indigo-400 mb-1">[[TITULO]]</h1>
        <p class="text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700">Prof. [[PROFESSOR]]</p>
        
        <div id="tela-pergunta">
            <h2 id="texto-pergunta" class="text-xl font-bold mb-4 text-center">A carregar...</h2>
            
            <!-- A FONTE DA DICA JÁ ESTÁ AUMENTADA AQUI -->
            <p id="dica-interacao" class="text-center text-red-500 text-2xl font-extrabold mb-4 animate-pulse italic">👉 Toque numa opção para responder!</p>
            
            <div id="opcoes-container" class="flex flex-col gap-3"></div>
            
            <div id="tela-feedback" class="hidden mt-6 p-4 rounded-xl text-center">
                <h3 id="feedback-titulo" class="font-bold text-lg mb-2"></h3>
                <p id="feedback-texto" class="text-sm"></p>
                <button onclick="proximaPergunta()" class="mt-4 w-full bg-indigo-600 py-3 rounded-xl">Continuar</button>
            </div>
        </div>
        
        <div id="tela-resultado" class="hidden text-center">
            <div class="text-6xl mb-4">🏆</div>
            <h2 class="text-2xl font-bold mb-2">Fim de Jogo!</h2>
            <p>Acertou <span id="pontuacao-final" class="font-bold text-indigo-400 text-2xl"></span> do quiz.</p>
        </div>
    </div>
    <script>
        const perguntas = [[JSON_PERGUNTAS]];
        let indiceAtual = 0; let acertos = 0; let respondido = false;
        
        function carregarPergunta() {
            respondido = false;
            const p = perguntas[indiceAtual];
            document.getElementById('texto-pergunta').innerText = p.pergunta;
            document.getElementById('tela-feedback').classList.add('hidden');
            const container = document.getElementById('opcoes-container');
            container.innerHTML = '';
            p.opcoes.forEach((opcao, index) => {
                const btn = document.createElement('button');
                btn.innerText = opcao;
                btn.className = 'btn-opcao w-full bg-slate-700 border-2 border-slate-600 text-left py-3 px-5 rounded-xl text-slate-200';
                btn.onclick = () => verificarResposta(index, btn);
                container.appendChild(btn);
            });
        }
        
        function verificarResposta(indiceSelecionado, botaoClicado) {
            if (respondido) return;
            respondido = true;
            document.getElementById('dica-interacao').style.display = 'none';
            const p = perguntas[indiceAtual];
            const telaFeedback = document.getElementById('tela-feedback');
            telaFeedback.classList.remove('hidden');
            
            if (indiceSelecionado === p.resposta_correta) {
                botaoClicado.classList.add('correto'); acertos++;
                telaFeedback.className = 'mt-6 p-4 rounded-xl text-center bg-green-900 block';
                document.getElementById('feedback-titulo').innerText = '✅ Correto!';
                document.getElementById('feedback-texto').innerText = p.explicacao;
            } else {
                botaoClicado.classList.add('errado');
                telaFeedback.className = 'mt-6 p-4 rounded-xl text-center bg-red-900 block';
                document.getElementById('feedback-titulo').innerText = '❌ Incorreto!';
                document.getElementById('feedback-texto').innerHTML = `A certa era: <b>${p.opcoes[p.resposta_correta]}</b>.<br><br>${p.explicacao}`;
            }
        }
        
        function proximaPergunta() {
            indiceAtual++;
            if (indiceAtual < perguntas.length) carregarPergunta();
            else mostrarResultado();
        }
        
        function mostrarResultado() {
            document.getElementById('tela-pergunta').classList.add('hidden');
            document.getElementById('tela-resultado').classList.remove('hidden');
            document.getElementById('pontuacao-final').innerText = Math.round((acertos / perguntas.length) * 100) + '%';
        }
        carregarPergunta();
    </script>
</body>
</html>"""
    return html_export.replace("[[TITULO]]", titulo_seguro).replace("[[PROFESSOR]]", nome_prof_seguro).replace("[[JSON_PERGUNTAS]]", json_str)

# ==========================================
# CONTROLO DE FLUXO DA APLICAÇÃO
# ==========================================
FORMATOS_PERMITIDOS = ["pdf", "docx", "pptx", "png", "jpg", "jpeg"]

if not st.session_state["autenticado"]:
    tela_login()
else:
    with st.sidebar:
        st.write(f"Conectado como: **{st.session_state['usuario_atual']}**")
        if st.button("Terminar Sessão", use_container_width=True):
            logout()

    st.title("🎲 Quizify")
    
    # === ESTA CAIXA VAI MOSTRAR OS MODELOS CORRETOS ===
    st.info("🔍 **Lista de Modelos Disponíveis (Copie um destes nomes se houver erro):**")
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                st.write(f"- `{m.name}`")
    except Exception as e:
        st.error(f"Erro ao listar: {e}")
    # ====================================================

    st.write("Transforme o seu material de estudo em jogos interativos!")

    aba_quiz, aba_flashcards = st.tabs(["📝 Gerar Quiz", "🃏 (Em breve)"])

    with aba_quiz:
        st.subheader("Configurações do Quiz")
        titulo_quiz = st.text_input("Título do Quiz", value="Desafio")
        nome_prof_quiz = st.text_input("Nome do Professor(a)", placeholder="Ex: Maria")
        qnt_perguntas = st.number_input("Número de perguntas", min_value=1, max_value=50, value=2)

        arquivo_final_quiz = st.file_uploader("Envie o ficheiro", type=FORMATOS_PERMITIDOS, accept_multiple_files=True)

        if arquivo_final_quiz and st.button("✨ Gerar Jogo", use_container_width=True):
            if verificar_seguranca(arquivo_final_quiz):
                with st.spinner("A analisar..."):
                    try:
                        texto_completo = ""
                        for arq in arquivo_final_quiz:
                            texto_completo += processar_arquivo(arq) + "\n\n"
                            
                        dados = gerar_quiz_da_ia(texto_completo, qnt_perguntas)
                        html_gerado = obter_html_jogo(dados, titulo_quiz, nome_prof_quiz)
                        
                        st.session_state["quiz_html_pronto"] = html_gerado
                        st.success("✅ Quiz criado!")
                    except Exception as e:
                        st.error(f"Erro: {e}")

        if st.session_state.get("quiz_html_pronto"):
            st.markdown("---")
            
            # === RENDERIZADOR PARA O iOS ===
            components.html(st.session_state["quiz_html_pronto"], height=750, scrolling=True)
            # ===============================
