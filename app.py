import streamlit as st
import google.generativeai as genai
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, storage
import PyPDF2
import docx
import pptx
from PIL import Image
import pytesseract
import json
import re
import time
import html
import uuid

# ==========================================
# CONFIGURAÇÃO DA IA E FIREBASE
# ==========================================
st.set_page_config(page_title="Quizify", layout="centered")

try:
    # 1. Configurar Gemini
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GEMINI_API_KEY)
    modelo = genai.GenerativeModel("gemini-3.8-flash")
    
    # 2. Configurar Firebase
    if not firebase_admin._apps:
        cert_dict = json.loads(st.secrets["FIREBASE_KEY"])
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': st.secrets["FIREBASE_BUCKET"]
        })
except Exception as e:
    st.error(f"Erro de configuração nos Secrets: {e}")
    st.stop()

# ==========================================
# FUNÇÃO DE UPLOAD PARA A NUVEM
# ==========================================
def fazer_upload_firebase(conteudo_html, prefixo="jogo"):
    try:
        nome_arquivo = f"{prefixo}_{uuid.uuid4().hex[:8]}.html"
        bucket = storage.bucket()
        blob = bucket.blob(nome_arquivo)
        # Faz o upload com o tipo de ficheiro correto
        blob.upload_from_string(conteudo_html, content_type='text/html')
        # Torna o link público para os alunos acederem
        blob.make_public()
        return blob.public_url
    except Exception as e:
        st.error(f"Erro ao gerar link de partilha: {e}")
        return None

# ==========================================
# VISUAL E SEGURANÇA
# ==========================================
esconder_menu = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """
st.markdown(esconder_menu, unsafe_allow_html=True)

USUARIOS_AUTORIZADOS = {"admin": "admin123", "escola_demo": "quiz2026", "professor": "aula123"}
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
if "quiz_pronto" not in st.session_state:
    st.session_state["quiz_pronto"] = None
if "link_quiz" not in st.session_state:
    st.session_state["link_quiz"] = None

def tela_login():
    st.markdown("<h2 style='text-align: center;'>🔐 Acesso Restrito - Quizify</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Insira as suas credenciais para aceder à plataforma.</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("form_login"):
            usuario = st.text_input("Utilizador / E-mail").strip().lower()
            senha = st.text_input("Palavra-passe", type="password").strip()
            botao_entrar = st.form_submit_button("Entrar", use_container_width=True)
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
    st.session_state["quiz_pronto"] = None
    st.session_state["link_quiz"] = None
    st.rerun()

def verificar_seguranca(arquivos):
    tamanho_total = sum([arq.size for arq in arquivos]) if isinstance(arquivos, list) else arquivos.size
    if tamanho_total > TAMANHO_MAXIMO_MB * 1024 * 1024:
        st.error(f"❌ O tamanho total excede o limite de {TAMANHO_MAXIMO_MB}MB.")
        return False
    if st.session_state["geracoes_nesta_sessao"] >= LIMITE_POR_SESSAO:
        st.error(f"⚠️ Limite de {LIMITE_POR_SESSAO} conteúdos atingido.")
        return False
    tempo_decorrido = time.time() - st.session_state["ultimo_uso"]
    if tempo_decorrido < COOLDOWN_SEGUNDOS:
        st.warning(f"⏳ Aguarde {int(COOLDOWN_SEGUNDOS - tempo_decorrido)}s.")
        return False
    return True

# ==========================================
# LEITURA E IA
# ==========================================
def extrair_texto_pdf(a): a.seek(0); return "".join([p.extract_text()+"\n" for p in PyPDF2.PdfReader(a).pages if p.extract_text()])
def extrair_texto_docx(a): a.seek(0); return "\n".join([p.text for p in docx.Document(a).paragraphs if p.text.strip()])
def extrair_texto_pptx(a):
    a.seek(0); t=[]
    for s in pptx.Presentation(a).slides:
        for sh in s.shapes:
            if sh.has_text_frame: t.extend([p.text.strip() for p in sh.text_frame.paragraphs if p.text.strip()])
    return "\n".join(t)
def extrair_texto_imagem(a):
    a.seek(0); img = Image.open(a).convert('L')
    try: return pytesseract.image_to_string(img, lang='por')
    except: return pytesseract.image_to_string(img)

def processar_arquivo(a):
    n = a.name.lower()
    if n.endswith(".pdf"): return extrair_texto_pdf(a)
    elif n.endswith(".docx"): return extrair_texto_docx(a)
    elif n.endswith(".pptx"): return extrair_texto_pptx(a)
    elif n.endswith((".png", ".jpg", ".jpeg")): return extrair_texto_imagem(a)
    else: raise ValueError("Formato não suportado.")

def gerar_quiz_da_ia(texto_base, num_perguntas):
    prompt = f"""Crie um quiz com {num_perguntas} perguntas do texto. Retorne APENAS um array JSON:
    [{{ "pergunta": "...", "opcoes": ["A", "B", "C", "D"], "resposta_correta": 1, "explicacao": "..." }}]
    --- TEXTO --- {texto_base[:15000]}"""
    txt = re.sub(r'```json\n?', '', modelo.generate_content(prompt).text)
    return json.loads(re.sub(r'```\n?', '', txt).strip())

def obter_html_jogo(json_perguntas, titulo_quiz, nome_professor):
    t_seg = html.escape(titulo_quiz)
    p_seg = html.escape(nome_professor)
    j_str = json.dumps(json_perguntas)

    html_export = """<!DOCTYPE html>
<html lang="pt-PT"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>[[TITULO]]</title><script src="https://cdn.tailwindcss.com"></script><style>body { font-family: sans-serif; } .btn-opcao { transition: all 0.2s; } .correto { background-color: #22c55e !important; color: white !important; } .errado { background-color: #ef4444 !important; color: white !important; }</style></head>
<body class="bg-slate-900 text-white flex items-center justify-center min-h-screen p-4">
    <audio id="som-palmas" preload="auto"><source src="https://www.myinstants.com/media/sounds/applause.mp3" type="audio/mpeg"></audio>
    <div class="w-full max-w-md bg-slate-800 rounded-2xl p-6 border border-slate-700">
        <h1 class="text-2xl font-extrabold text-center text-indigo-400 mb-1">[[TITULO]]</h1>
        <p class="text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700">Prof. [[PROFESSOR]]</p>
        <div id="tela-pergunta"><h2 id="texto-pergunta" class="text-xl font-bold mb-4 text-center">A carregar...</h2><p id="dica-interacao" class="text-center text-red-500 text-2xl font-extrabold mb-4 animate-pulse italic">👉 Toque numa opção para responder!</p><div id="opcoes-container" class="flex flex-col gap-3"></div><div id="tela-feedback" class="hidden mt-6 p-4 rounded-xl text-center"><h3 id="feedback-titulo" class="font-bold text-lg mb-2"></h3><p id="feedback-texto" class="text-sm"></p><button onclick="proximaPergunta()" class="mt-4 w-full bg-indigo-600 py-3 rounded-xl">Continuar</button></div></div>
        <div id="tela-resultado" class="hidden text-center"><div class="text-6xl mb-4">🏆</div><h2 class="text-2xl font-bold mb-2">Fim de Jogo!</h2><p>Acertou <span id="pontuacao-final" class="font-bold text-indigo-400 text-2xl"></span> do quiz.</p><button onclick="location.reload()" class="mt-6 w-full bg-indigo-600 py-3 rounded-xl">Jogar Novamente</button></div>
    </div>
    <script>
        const perguntas = [[JSON_PERGUNTAS]]; let indiceAtual = 0; let acertos = 0; let respondido = false;
        function carregarPergunta() { respondido = false; const p = perguntas[indiceAtual]; document.getElementById('texto-pergunta').innerText = p.pergunta; document.getElementById('tela-feedback').classList.add('hidden'); const c = document.getElementById('opcoes-container'); c.innerHTML = ''; p.opcoes.forEach((op, i) => { const btn = document.createElement('button'); btn.innerText = op; btn.className = 'btn-opcao w-full bg-slate-700 border-2 border-slate-600 text-left py-3 px-5 rounded-xl text-slate-200'; btn.onclick = () => verificarResposta(i, btn); c.appendChild(btn); }); }
        function verificarResposta(iSel, btn) { if (respondido) return; respondido = true; document.getElementById('dica-interacao').style.display = 'none'; const p = perguntas[indiceAtual]; const telaF = document.getElementById('tela-feedback'); telaF.classList.remove('hidden'); if (iSel === p.resposta_correta) { btn.classList.add('correto'); acertos++; telaF.className = 'mt-6 p-4 rounded-xl text-center bg-green-900 block'; document.getElementById('feedback-titulo').innerText = '✅ Correto!'; document.getElementById('feedback-texto').innerText = p.explicacao; } else { btn.classList.add('errado'); telaF.className = 'mt-6 p-4 rounded-xl text-center bg-red-900 block'; document.getElementById('feedback-titulo').innerText = '❌ Incorreto!'; document.getElementById('feedback-texto').innerHTML = `A certa era: <b>${p.opcoes[p.resposta_correta]}</b>.<br><br>${p.explicacao}`; } }
        function proximaPergunta() { indiceAtual++; if (indiceAtual < perguntas.length) carregarPergunta(); else mostrarResultado(); }
        function mostrarResultado() { document.getElementById('som-palmas').play().catch(e=>{}); document.getElementById('tela-pergunta').classList.add('hidden'); document.getElementById('tela-resultado').classList.remove('hidden'); document.getElementById('pontuacao-final').innerText = Math.round((acertos / perguntas.length) * 100) + '%'; }
        carregarPergunta();
    </script>
</body></html>"""
    return html_export.replace("[[TITULO]]", t_seg).replace("[[PROFESSOR]]", p_seg).replace("[[JSON_PERGUNTAS]]", j_str)

# ==========================================
# INTERFACE PRINCIPAL
# ==========================================
FORMATOS = ["pdf", "docx", "pptx", "png", "jpg", "jpeg"]

if not st.session_state["autenticado"]:
    tela_login()
else:
    with st.sidebar:
        st.write(f"Utilizador: **{st.session_state['usuario_atual']}**")
        if st.button("Sair", use_container_width=True): logout()

    st.title("🎲 Quizify")
    st.subheader("Configurações do Quiz")
    
    t_quiz = st.text_input("Título", value="Desafio de Conhecimento")
    n_prof = st.text_input("Professor(a)", placeholder="Ex: Maria")
    q_perg = st.number_input("Perguntas", min_value=1, max_value=50, value=5)
    arquivos = st.file_uploader("Ficheiros", type=FORMATOS, accept_multiple_files=True)

    if arquivos and st.button("✨ Gerar e Publicar Jogo", use_container_width=True):
        if verificar_seguranca(arquivos):
            with st.spinner("A gerar o jogo e a publicar na nuvem..."):
                try:
                    txt = "".join([processar_arquivo(a)+"\n" for a in arquivos])
                    dados = gerar_quiz_da_ia(txt, q_perg)
                    html_final = obter_html_jogo(dados, t_quiz, n_prof)
                    
                    st.session_state["quiz_pronto"] = html_final
                    # Faz o upload e guarda o link público
                    st.session_state["link_quiz"] = fazer_upload_firebase(html_final)
                    st.session_state["ultimo_uso"] = time.time()
                    st.session_state["geracoes_nesta_sessao"] += 1
                    
                    st.success("✅ Jogo publicado com sucesso!")
                except Exception as e:
                    st.error(f"Erro: {e}")

    if st.session_state.get("quiz_pronto"):
        st.markdown("---")
        
        # Bloco de Partilha (Link para iOS)
        if st.session_state.get("link_quiz"):
            st.info("📱 **LINK PARA ALUNOS (Funciona em iOS e Android):**")
            st.code(st.session_state["link_quiz"], language="text")
            st.write("Copie o link acima e cole no WhatsApp. Os alunos jogarão diretamente no navegador sem precisarem descarregar nada!")

        # Jogo na tela
        components.html(st.session_state["quiz_pronto"], height=750, scrolling=True)

        # Botão para Android/PC
        nome_seg = re.sub(r'[^\w\s-]', '', t_quiz).strip().replace(' ', '_') or "quiz"
        st.download_button("📥 Descarregar Ficheiro Offline (Android/PC)", st.session_state["quiz_pronto"], f"{nome_seg}.html", "text/html", use_container_width=True)
