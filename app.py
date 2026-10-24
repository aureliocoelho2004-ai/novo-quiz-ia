import streamlit as st
import google.generativeai as genai
import streamlit.components.v1 as components
import firebase_admin
from firebase_admin import credentials, storage
import PyPDF2
import docx
import pptx
from PIL import Image
import io
import json
import re
import time
import html
import uuid
import os

st.set_page_config(page_title="Quizify", layout="centered")

def obter_segredo(chave):
    if chave in os.environ: return os.environ[chave]
    try: return st.secrets[chave]
    except Exception: raise ValueError(f"Variavel ausente: {chave}")

try:
    genai.configure(api_key=obter_segredo("GEMINI_API_KEY"))
    modelo = genai.GenerativeModel("gemini-3.8-flash")
    
    if not firebase_admin._apps:
        cert_dict = json.loads(obter_segredo("FIREBASE_KEY"))
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {'storageBucket': obter_segredo("FIREBASE_BUCKET")})
except Exception as e:
    st.error(f"Erro de infraestrutura: {e}")
    st.stop()

def carregar_usuarios():
    padrao = {"admin": "admin123", "professor": "aula123"}
    try:
        blob = storage.bucket().blob("usuarios.json")
        if blob.exists(): return json.loads(blob.download_as_string())
    except: pass
    return padrao

def salvar_usuarios(dicionario_usuarios):
    try:
        blob = storage.bucket().blob("usuarios.json")
        blob.upload_from_string(json.dumps(dicionario_usuarios), content_type='application/json')
        return True
    except Exception as e:
        return False

if "dicionario_usuarios" not in st.session_state:
    st.session_state["dicionario_usuarios"] = carregar_usuarios()

def fazer_upload_firebase(conteudo_html, prefixo="quizify"):
    try:
        nome_arquivo = f"{prefixo}_{uuid.uuid4().hex[:8]}.html"
        blob = storage.bucket().blob(nome_arquivo)
        blob.upload_from_string(conteudo_html, content_type='text/html')
        blob.make_public()
        return blob.public_url
    except Exception:
        return None

st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)

if "autenticado" not in st.session_state: st.session_state["autenticado"] = False
if "ultimo_uso" not in st.session_state: st.session_state["ultimo_uso"] = 0.0
if "conteudo_pronto" not in st.session_state: st.session_state["conteudo_pronto"] = None
if "link_conteudo" not in st.session_state: st.session_state["link_conteudo"] = None
if "usuario_atual" not in st.session_state: st.session_state["usuario_atual"] = ""

def verificar_seguranca(arquivos):
    return True

def processar_arquivo(a):
    n = a.name.lower()
    a.seek(0)
    if n.endswith(".pdf"):
        return "".join([p.extract_text()+"\n" for p in PyPDF2.PdfReader(a).pages if p.extract_text()])
    elif n.endswith(".docx"):
        return "\n".join([p.text for p in docx.Document(a).paragraphs if p.text.strip()])
    elif n.endswith(".pptx"):
        t = []
        prs = pptx.Presentation(a)
        for s in prs.slides:
            for sh in s.shapes:
                if sh.has_text_frame:
                    for p in sh.text_frame.paragraphs:
                        if p.text.strip(): t.append(p.text.strip())
                if sh.has_table:
                    for row in sh.table.rows:
                        for cell in row.cells:
                            if cell.text.strip(): t.append(cell.text.strip())
        return "\n".join(t)
    elif n.endswith((".png", ".jpg", ".jpeg")):
        try:
            img = Image.open(a).convert("RGB")
            img.thumbnail((600, 600))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=60)
            buffer.seek(0)
            img_otimizada = Image.open(buffer)
            resposta_visao = modelo.generate_content(["Transcreve todo o texto visível nesta imagem.", img_otimizada])
            return resposta_visao.text
        except Exception:
            return ""
    return ""

def gerar_dados_ia(texto_base, quantidade, tipo_conteudo):
    if not texto_base.strip(): raise ValueError("O ficheiro enviado não contém texto legível.")
    if tipo_conteudo == "Quiz":
        p = f"Crie um quiz com {quantidade} perguntas focadas no texto. Retorne APENAS um array JSON: [{{'pergunta':'...','opcoes':['A','B','C','D'],'resposta_correta':1,'explicacao':'...'}}] TEXTO: {texto_base[:15000]}"
    else:
        p = f"Crie {quantidade} flashcards extraindo os conceitos mais importantes. Retorne APENAS um array JSON: [{{'frente':'...','verso':'...'}}] TEXTO: {texto_base[:15000]}"
    txt = re.sub(r'```json\n?', '', modelo.generate_content(p).text)
    return json.loads(re.sub(r'```\n?', '', txt).strip())

def obter_html_jogo(json_dados, titulo, professor):
    t_seg = html.escape(titulo)
    p_seg = html.escape(professor)
    j_str = json.dumps(json_dados)

    html_export = """<!DOCTYPE html>
<html lang="pt-PT">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[[TITULO]]</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-900 text-white flex items-center justify-center min-h-screen p-4">
    <div class="w-full max-w-md bg-slate-800 rounded-2xl p-6 border border-slate-700">
        <h1 class="text-2xl font-extrabold text-center text-indigo-400 mb-1">[[TITULO]]</h1>
        <p class="text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700">Prof. [[PROFESSOR]]</p>
        
        <!-- TELA DA PERGUNTA -->
        <div id="tela-pergunta" style="display: block;">
            <h2 id="texto-pergunta" class="text-xl font-bold mb-4 text-center">A carregar...</h2>
            
            <!-- A DICA INICIAL GARANTIDA -->
            <p id="dica-interacao" style="display: block; color: #ef4444; text-align: center; font-weight: 800; font-size: 1.1rem; font-style: italic; margin-bottom: 1rem; animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;">👉 Toque numa opção para responder!</p>
            
            <div id="opcoes-container" class="flex flex-col gap-3"></div>
            
            <!-- FEEDBACK (CERTO/ERRADO) -->
            <div id="tela-feedback" style="display: none; margin-top: 1.5rem; padding: 1rem; border-radius: 0.75rem; text-align: center;">
                <h3 id="feedback-titulo" class="font-bold text-lg mb-2"></h3>
                <p id="feedback-texto" class="text-sm mb-4"></p>
                <button onclick="proximaPergunta()" class="w-full bg-indigo-600 py-3 rounded-xl font-bold text-white shadow-lg">➡️ Continuar</button>
            </div>
        </div>
        
        <!-- TELA DE FIM DE JOGO -->
        <div id="tela-resultado" style="display: none; text-align: center;">
            <div class="text-6xl mb-4">🏆</div>
            <h2 class="text-2xl font-bold mb-2">Fim de Jogo!</h2>
            <p class="mb-6">Acertou <span id="pontuacao-final" class="font-bold text-indigo-400 text-2xl"></span> do quiz.</p>
            
            <!-- OS DOIS BOTÕES -->
            <div class="flex flex-col gap-3">
                <button onclick="jogarTudo()" class="w-full bg-indigo-600 py-3 rounded-xl font-bold text-white shadow-lg">🔄 Tentar o Quiz Completo</button>
                <button id="btn-erradas" onclick="jogarErradas()" style="display: none; background-color: #d97706;" class="w-full py-3 rounded-xl font-bold text-white shadow-lg mt-2">🎯 Refazer Apenas as Erradas</button>
            </div>
        </div>
    </div>

    <script>
        const perguntasOriginais = [[JSON_DADOS]]; 
        let perguntasAtuais = [...perguntasOriginais];
        let erradas = [];
        let indice = 0; 
        let acertos = 0; 
        let bloqueado = false;

        function renderizar() {
            bloqueado = false;
            document.getElementById('tela-feedback').style.display = 'none';
            document.getElementById('dica-interacao').style.display = 'block';
            
            const p = perguntasAtuais[indice];
            document.getElementById('texto-pergunta').innerText = "(" + (indice + 1) + "/" + perguntasAtuais.length + ") " + p.pergunta;
            
            const divOpc = document.getElementById('opcoes-container');
            divOpc.innerHTML = '';
            
            p.opcoes.forEach((texto, i) => {
                const btn = document.createElement('button');
                btn.innerText = texto;
                btn.className = 'w-full bg-slate-700 border-2 border-slate-600 text-left py-3 px-5 rounded-xl text-white font-bold text-lg mb-3';
                btn.onclick = () => responder(i, btn, p);
                divOpc.appendChild(btn);
            });
        }

        function responder(iSel, btn, pAtual) {
            if(bloqueado) return;
            bloqueado = true;
            
            document.getElementById('dica-interacao').style.display = 'none';
            const telaF = document.getElementById('tela-feedback');
            telaF.style.display = 'block';
            
            if(iSel === pAtual.resposta_correta) {
                btn.style.backgroundColor = '#22c55e';
                acertos++;
                telaF.style.backgroundColor = '#14532d'; // Verde escuro
                document.getElementById('feedback-titulo').innerText = '✅ Correto!';
                document.getElementById('feedback-texto').innerText = pAtual.explicacao;
            } else {
                btn.style.backgroundColor = '#ef4444';
                telaF.style.backgroundColor = '#7f1d1d'; // Vermelho escuro
                document.getElementById('feedback-titulo').innerText = '❌ Incorreto!';
                document.getElementById('feedback-texto').innerHTML = "A resposta certa era: <b>" + pAtual.opcoes[pAtual.resposta_correta] + "</b>.<br><br>" + pAtual.explicacao;
                
                if(!erradas.includes(pAtual)) {
                    erradas.push(pAtual);
                }
            }
        }

        function proximaPergunta() {
            indice++;
            if(indice < perguntasAtuais.length) {
                renderizar();
            } else {
                document.getElementById('tela-pergunta').style.display = 'none';
                document.getElementById('tela-resultado').style.display = 'block';
                
                let pct = Math.round((acertos / perguntasAtuais.length) * 100);
                document.getElementById('pontuacao-final').innerText = pct + '%';
                
                if(erradas.length > 0) {
                    document.getElementById('btn-erradas').style.display = 'block';
                } else {
                    document.getElementById('btn-erradas').style.display = 'none';
                }
            }
        }

        function jogarTudo() {
            perguntasAtuais = [...perguntasOriginais];
            erradas = [];
            indice = 0;
            acertos = 0;
            document.getElementById('tela-resultado').style.display = 'none';
            document.getElementById('tela-pergunta').style.display = 'block';
            renderizar();
        }

        function jogarErradas() {
            perguntasAtuais = [...erradas];
            erradas = [];
            indice = 0;
            acertos = 0;
            document.getElementById('tela-resultado').style.display = 'none';
            document.getElementById('tela-pergunta').style.display = 'block';
            renderizar();
        }

        renderizar();
    </script>
</body></html>"""
    return html_export.replace("[[TITULO]]", t_seg).replace("[[PROFESSOR]]", p_seg).replace("[[JSON_DADOS]]", j_str)

def obter_html_flashcards(json_dados, titulo, professor):
    t_seg = html.escape(titulo)
    p_seg = html.escape(professor)
    j_str = json.dumps(json_dados)
    
    html_export = """<!DOCTYPE html>
<html lang="pt-PT"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>[[TITULO]]</title><script src="https://cdn.tailwindcss.com"></script>
<style>.perspective { perspective: 1000px; } .flip-card-inner { transition: transform 0.6s; transform-style: preserve-3d; position: relative; width: 100%; height: 100%; } .flipped .flip-card-inner { transform: rotateY(180deg); } .flip-card-front, .flip-card-back { backface-visibility: hidden; position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; padding: 2rem; text-align: center; border-radius: 1rem; } .flip-card-back { transform: rotateY(180deg); background-color: #4f46e5; }</style></head>
<body class="bg-slate-900 text-white flex items-center justify-center min-h-screen p-4">
    <div class="w-full max-w-md bg-slate-800 rounded-2xl p-6 border border-slate-700 flex flex-col items-center">
        <h1 class="text-2xl font-extrabold text-center text-indigo-400 mb-1">[[TITULO]]</h1>
        <p class="text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700 w-full">Prof. [[PROFESSOR]]</p>
        <p class="text-slate-400 mb-2 text-sm">Cartão <span id="contador">1</span> de <span id="total"></span></p>
        <div id="card" class="perspective w-full h-64 mb-6 cursor-pointer" onclick="virarCard()">
            <div class="flip-card-inner bg-slate-700 border-2 border-slate-600 rounded-2xl shadow-xl">
                <div class="flip-card-front"><h2 id="frente" class="text-xl font-bold"></h2></div>
                <div class="flip-card-back"><p id="verso" class="text-lg font-medium"></p></div>
            </div>
        </div>
        <p class="text-center text-red-500 font-bold mb-4 animate-pulse">👉 Toque no cartão para virar!</p>
        <div class="flex justify-between w-full gap-4">
            <button onclick="mudar(-1)" class="flex-1 bg-slate-700 py-3 rounded-xl font-bold hover:bg-slate-600">Anterior</button>
            <button onclick="mudar(1)" class="flex-1 bg-indigo-600 py-3 rounded-xl font-bold hover:bg-indigo-500">Próximo</button>
        </div>
    </div>
    <script>
        const cards = [[JSON_DADOS]]; let indice = 0; document.getElementById('total').innerText = cards.length;
        function carregar() { document.getElementById('card').classList.remove('flipped'); setTimeout(() => { document.getElementById('frente').innerText = cards[indice].frente; document.getElementById('verso').innerText = cards[indice].verso; document.getElementById('contador').innerText = indice + 1; }, 150); }
        function virarCard() { document.getElementById('card').classList.toggle('flipped'); }
        function mudar(dir) { if (indice + dir >= 0 && indice + dir < cards.length) { indice += dir; carregar(); } }
        carregar();
    </script>
</body></html>"""
    return html_export.replace("[[TITULO]]", t_seg).replace("[[PROFESSOR]]", p_seg).replace("[[JSON_DADOS]]", j_str)

if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acesso Restrito</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("form_login"):
            usuario = st.text_input("Utilizador").strip().lower()
            senha = st.text_input("Palavra-passe", type="password").strip()
            if st.form_submit_button("Entrar", use_container_width=True):
                db_usuarios = st.session_state["dicionario_usuarios"]
                if usuario in db_usuarios and db_usuarios[usuario] == senha:
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_atual"] = usuario
                    st.rerun()
                else:
                    st.error("Acesso negado.")
else:
    with st.sidebar:
        st.write(f"Logado como: **{st.session_state['usuario_atual']}**")
        if st.session_state["usuario_atual"] == "admin":
            st.markdown("---")
            st.subheader("👑 Painel Master")
            n_usu = st.text_input("Novo Utilizador").strip().lower()
            n_sen = st.text_input("Nova Senha").strip()
            if st.button("Criar Acesso", use_container_width=True):
                if n_usu and n_sen:
                    st.session_state["dicionario_usuarios"][n_usu] = n_sen
                    salvar_usuarios(st.session_state["dicionario_usuarios"])
                    st.success("Criado!")
            st.write("Utilizadores:")
            for u in st.session_state["dicionario_usuarios"].keys():
                st.write(f"- {u}")
        st.markdown("---")
        if st.button("Sair", use_container_width=True):
            st.session_state["autenticado"] = False
            st.rerun()

    st.title("🎲 Quizify")
    tipo_conteudo = st.radio("Criar:", ["Quiz", "Flashcards"], horizontal=True)
    t_titulo = st.text_input("Título", value="Desafio de Conhecimento")
    n_prof = st.text_input("Professor(a)")
    q_itens = st.number_input("Quantidade", min_value=1, max_value=50, value=5)
    
    arquivos = st.file_uploader("Ficheiros", type=["pdf", "docx", "pptx", "png", "jpg", "jpeg"], accept_multiple_files=True)

    if arquivos and st.button(f"Gerar {tipo_conteudo}", use_container_width=True):
        with st.spinner("A gerar conteúdo novo..."):
            txt = "".join([processar_arquivo(a)+"\n" for a in arquivos])
            dados = gerar_dados_ia(txt, q_itens, tipo_conteudo)
            
            if tipo_conteudo == "Quiz":
                html_final = obter_html_jogo(dados, t_titulo, n_prof)
                prefixo = "quiz"
            else:
                html_final = obter_html_flashcards(dados, t_titulo, n_prof)
                prefixo = "flash"
            
            st.session_state["conteudo_pronto"] = html_final
            st.session_state["link_conteudo"] = fazer_upload_firebase(html_final, prefixo)

    if st.session_state.get("conteudo_pronto"):
        st.markdown("---")
        if st.session_state.get("link_conteudo"):
            st.info("📱 LINK DIRETO:")
            st.code(st.session_state["link_conteudo"], language="text")

        st.download_button("📥 Descarregar HTML", st.session_state["conteudo_pronto"], "conteudo.html", "text/html", use_container_width=True)
        components.html(st.session_state["conteudo_pronto"], height=750, scrolling=True)
