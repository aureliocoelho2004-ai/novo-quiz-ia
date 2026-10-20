import streamlit as st
import google.generativeai as genai
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
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
modelo = genai.GenerativeModel("gemini-3.8-flash") 

# ==========================================
# CONTROLO DE ACESSO E SEGURANÇA (RATE LIMIT)
# ==========================================
USUARIOS_AUTORIZADOS = {
    "admin": "admin123",           
    "escola_demo": "quiz2026",     
    "professor": "aula123"         
}

TAMANHO_MAXIMO_MB = 10
COOLDOWN_SEGUNDOS = 30
LIMITE_POR_SESSAO = 15

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
    st.session_state["geracoes_nesta_sessao"] = 0
    st.session_state["quiz_html_pronto"] = None
    st.session_state["flash_html_pronto"] = None
    st.rerun()

def verificar_seguranca(arquivo):
    if arquivo.size > TAMANHO_MAXIMO_MB * 1024 * 1024:
        st.error(f"❌ Segurança: O ficheiro excede o limite de {TAMANHO_MAXIMO_MB}MB.")
        return False
        
    if st.session_state["geracoes_nesta_sessao"] >= LIMITE_POR_SESSAO:
        st.error(f"❌ Limite atingido: Já gerou {LIMITE_POR_SESSAO} conteúdos nesta sessão.")
        return False
        
    tempo_decorrido = time.time() - st.session_state["ultimo_uso"]
    if tempo_decorrido < COOLDOWN_SEGUNDOS:
        st.warning(f"⏳ Aguarde {int(COOLDOWN_SEGUNDOS - tempo_decorrido)} segundos antes de gerar um novo conteúdo.")
        return False
        
    return True

# ==========================================
# FUNÇÕES DE EXTRAÇÃO DE TEXTO
# ==========================================
def extrair_texto_pdf(arquivo):
    leitor = PyPDF2.PdfReader(arquivo)
    texto = ""
    for pagina in leitor.pages:
        if pagina.extract_text():
            texto += pagina.extract_text() + "\n"
    return texto

def extrair_texto_docx(arquivo):
    doc = docx.Document(arquivo)
    texto = "\n".join([paragrafo.text for paragrafo in doc.paragraphs])
    return texto

def extrair_texto_pptx(arquivo):
    apresentacao = pptx.Presentation(arquivo)
    texto = ""
    for slide in apresentacao.slides:
        for forma in slide.shapes:
            if hasattr(forma, "text"):
                texto += forma.text + "\n"
    return texto

def extrair_texto_imagem(arquivo):
    imagem = Image.open(arquivo)
    
    tamanho_maximo = (1600, 1600)
    imagem.thumbnail(tamanho_maximo, Image.Resampling.LANCZOS)
    imagem = imagem.convert('L')
    
    try:
        texto = pytesseract.image_to_string(imagem, lang='por')
    except Exception:
        texto = pytesseract.image_to_string(imagem)
    return texto

def processar_arquivo(arquivo):
