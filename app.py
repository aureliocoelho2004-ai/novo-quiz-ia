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
        st.sidebar.error(f"Erro ao guardar: {e}")
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
if "geracoes_nesta_sessao" not in st.session_state: st.session_state["geracoes_nesta_sessao"] = 0
if "conteudo_pronto" not in st.session_state: st.session_state["conteudo_pronto"] = None
if "link_conteudo" not in st.session_state: st.session_state["link_conteudo"] = None
if "usuario_atual" not in st.session_state: st.session_state["usuario_atual"] = ""

def verificar_seguranca(arquivos):
    return True

def processar_arquivo(a):
    n = a.name.lower()
    a.seek(0)
    if n.endswith(".pdf"): return "".join([p.extract_text()+"\n" for p in PyPDF2.PdfReader(a).pages if p.extract_text()])
    elif n.endswith(".docx"): return "\n".join([p.text for p in docx.Document(a).paragraphs if p.text.strip()])
    elif n.endswith(".pptx"):
        t = []
        for s in pptx.Presentation(a).slides:
            for sh in s.shapes:
                if sh.has_text_frame: t.extend([p.text.strip() for p in sh.text_frame.paragraphs if p.text.strip()])
        return "\n".join(t)
    elif n.endswith((".png", ".jpg", ".jpeg")):
        try:
            img = Image.open(a).convert("RGB")
            img.thumbnail((600, 600))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=60)
            buffer.seek(0)
            img_otimizada = Image.open(buffer)

            resposta_visao = modelo.generate_content([
                "Transcreve todo o texto visível nesta imagem com precisão.", 
                img_otimizada
            ])
            return resposta_visao.text
        except Exception as e:
            return f"[Erro ao ler imagem com IA: {e}]"
    return ""

def gerar_dados_ia(texto_base, quantidade, tipo_conteudo):
    if tipo_conteudo == "Quiz":
        p = f"Crie um quiz com {quantidade} perguntas focadas no texto. Retorne APENAS um array JSON: [{{'pergunta':'...','opcoes':['A','B','C','D'],'resposta_correta':1,'explicacao':'...'}}] TEXTO: {texto_base[:15000]}"
    else:
        p = f"Crie {quantidade} flashcards extraindo os conceitos mais importantes. Retorne APENAS um array JSON: [{{'frente':'...','verso':'...'}}] TEXTO: {texto_base[:15000]}"
    txt = re.sub(r'```json\n?', '', modelo.generate_content(p).text)
    return json.loads(re.sub(r'```\n?', '', txt).strip())

def construir_html_jogo(json_dados, titulo, professor):
    linhas = [
        "<!DOCTYPE html><html lang='pt-PT'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"<title>{html.escape(titulo)}</title><script src='https://cdn.tailwindcss.com'></script>",
        "<style>.correto{background-color:#22c55e!important;color:white!important;}.errado{background-color:#ef4444!important;color:white!important;}</style></head>",
        "<body class='bg-slate-900 text-white flex items-center justify-center min-h-screen p-4'>",
        "<div class='w-full max-w-md bg-slate-800 rounded-2xl p-6 border border-slate-700'>",
        f"<h1 class='text-2xl font-extrabold text-center text-indigo-400 mb-1'>{html.escape(titulo)}</h1>",
        f"<p class='text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700'>Prof. {html.escape(professor)}</p>",
        "<div id='tela-p'><h2 id='t-perg' class='text-xl font-bold mb-4 text-center'>A carregar...</h2><div id='opc' class='flex flex-col gap-3'></div>",
        "<div id='tela-f' class='hidden mt-6 p-4 rounded-xl text-center'><h3 id='f-tit' class='font-bold text-lg mb-2'></h3><p id='f-txt' class='text-sm mb-4'></p>",
        "<button onclick='prox()' class='w-full bg-indigo-600 hover:bg-indigo-500 py-3 rounded-xl font-bold text-white shadow-lg cursor-pointer'>➡️ Seguinte Pergunta</button></div></div>",
        "<div id='tela-r' class='hidden text-center'><div class='text-6xl mb-4'>🏆</div><h2 class='text-2xl font-bold mb-2'>Fim de Jogo!</h2>",
        "<p class='mb-6'>Acertou <span id='p-fin' class='font-bold text-indigo-400 text-2xl'></span> do quiz.</p>",
        "<div class='flex flex-col gap-3'>",
        "<button onclick='reiniciarCompleto()' class='w-full bg-indigo-600 hover:bg-indigo-500 py-3 rounded-xl font-bold text-white'>🔄 Tentar o Quiz Completo</button>",
        "<button id='btn-erradas' onclick='reiniciarErradas()' class='hidden w-full bg-amber-600 hover:bg-amber-500 py-3 rounded-xl font-bold text-white'>🎯 Refazer Apenas as Erradas</button>",
        "</div></div></div>",
        "<script>",
        f"let pergsOriginais={json.dumps(json_dados)}; let pergs = [...pergsOriginais]; let perguntasErradas = []; let ind=0; let acertos=0; let resp=false;",
        "function carregar(){resp=false;const p=pergs[ind];document.getElementById('t-perg').innerText=p.pergunta;document.getElementById('tela-f').classList.add('hidden');",
        "const c=document.getElementById('opc');c.innerHTML='';p.opcoes.forEach((o,i)=>{const b=document.createElement('button');b.innerText=o;",
        "b.className='w-full bg-slate-700 border-2 border-slate-600 text-left py-3 px-5 rounded-xl text-white font-bold text-lg hover:bg-slate-600';b.onclick=()=>verificar(i,b);c.appendChild(b);});}",
        "function verificar(iS,b){if(resp)return;resp=true;const p=pergs[ind];const tf=document.getElementById('tela-f');tf.classList.remove('hidden');",
        "if(iS===p.resposta_correta){b.classList.add('correto');acertos++;tf.className='mt-6 p-4 rounded-xl text-center bg-green-900 block';document.getElementById('f-tit').innerText='✅ Correto!';document.getElementById('f-txt').innerText=p.explicacao;}",
        "else{b.classList.add('errado');tf.className='mt-6 p-4 rounded-xl text-center bg-red-900 block';document.getElementById('f-tit').innerText='❌ Incorreto!';document.getElementById('f-txt').innerHTML=`A certa era: <b>${p.opcoes[p.resposta_correta]}</b>.<br><br>${p.explicacao}`;",
        "if(!perguntasErradas.includes(p)) { perguntasErradas.push(p); }}}",
        "function prox(){ind++;if(ind<pergs.length)carregar();else mostrar();}",
        "function mostrar(){document.getElementById('tela-p').classList.add('hidden');document.getElementById('tela-r').classList.remove('hidden');document.getElementById('p-fin').innerText=Math.round((acertos/pergsOriginais.length)*100)+'%';",
        "const btnErradas = document.getElementById('btn-erradas');if(perguntasErradas.length > 0){btnErradas.classList.remove('hidden');}else{btnErradas.classList.add('hidden');}}",
        "function reiniciarCompleto(){pergs = [...pergsOriginais]; perguntasErradas = []; ind = 0; acertos = 0; document.getElementById('tela-r').classList.add('hidden'); document.getElementById('tela-p').classList.remove('hidden'); carregar();}",
        "function reiniciarErradas(){pergs = [...perguntasErradas]; perguntasErradas = []; ind = 0; acertos = pergsOriginais.length - pergs.length; document.getElementById('tela-r').classList.add('hidden'); document.getElementById('tela-p').classList.remove('hidden'); carregar();}",
        "carregar();</script></body></html>"
    ]
    return "".join(linhas)

def construir_html_flash(json_dados, titulo, professor):
    linhas = [
        "<!DOCTYPE html><html lang='pt-PT'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        f"<title>{html.escape(titulo)}</title><script src='https://cdn.tailwindcss.com'></script>",
        "<style>.pers{perspective:1000px;}.flip-in{transition:transform 0.6s;transform-style:preserve-3d;position:relative;width:100%;height:100%;}",
        ".flipped .flip-in{transform:rotateY(180deg);}.f-front,.f-back{backface-visibility:hidden;position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;padding:2rem;text-align:center;border-radius:1rem;}",
        ".f-back{transform:rotateY(180deg);background-color:#4f46e5;}</style></head>",
        "<body class='bg-slate-900 text-white flex items-center justify-center min-h-screen p-4'><div class='w-full max-w-md bg-slate-800 rounded-2xl p-6 flex flex-col items-center'>",
        f"<h1 class='text-2xl font-extrabold text-center text-indigo-400 mb-1'>{html.escape(titulo)}</h1>",
        f"<p class='text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700 w-full'>Prof. {html.escape(professor)}</p>",
        "<p class='text-slate-400 mb-2 text-sm'>Cartão <span id='c'>1</span> de <span id='t'></span></p>",
        "<div id='card' class='pers w-full h-64 mb-6 cursor-pointer' onclick='virar()'><div class='flip-in bg-slate-700 border-2 border-slate-600 rounded-2xl shadow-xl'>",
        "<div class='f-front'><h2 id='fr' class='text-xl font-bold'></h2></div><div class='f-back'><p id='bk' class='text-lg font-medium'></p></div></div></div>",
        "<div class='flex justify-between w-full gap-4'><button onclick='mudar(-1)' class='flex-1 bg-slate-700 py-3 rounded-xl font-bold'>Anterior</button>",
        "<button onclick='mudar(1)' class='flex-1 bg-indigo-600 py-3 rounded-xl font-bold'>Próximo</button></div></div>",
        "<script>",
        f"const cards={json.dumps(json_dados)};let ind=0;document.getElementById('t').innerText=cards.length;",
        "function carregar(){document.getElementById('card').classList.remove('flipped');setTimeout(()=>{document.getElementById('fr').innerText=cards[ind].frente;",
        "document.getElementById('bk').innerText=cards[ind].verso;document.getElementById('c').innerText=ind+1;},150);}",
        "function virar(){document.getElementById('card').classList.toggle('flipped');}",
        "function mudar(dir){if(ind+dir>=0&&ind+dir<cards.length){ind+=dir;carregar();}}carregar();</script></body></html>"
    ]
    return "".join(linhas)

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
            if st.button("Adicionar Utilizador", use_container_width=True):
                if n_usu and n_sen:
                    st.session_state["dicionario_usuarios"][n_usu] = n_sen
                    if salvar_usuarios(st.session_state["dicionario_usuarios"]):
                        st.success(f"Utilizador '{n_usu}' criado!")
                else:
                    st.error("Preencha ambos os campos.")
            
            st.markdown("---")
            st.write("Utilizadores Atuais:")
            for u in st.session_state["dicionario_usuarios"].keys():
                st.write(f"- {u}")

        st.markdown("---")
        if st.button("Sair", use_container_width=True):
            for key in ["autenticado", "usuario_atual", "conteudo_pronto", "link_conteudo"]:
                st.session_state[key] = None
            st.session_state["autenticado"] = False
            st.rerun()

    st.title("🎲 Quizify")
    tipo_conteudo = st.radio("Criar:", ["Quiz", "Flashcards"], horizontal=True)
    t_titulo = st.text_input("Título", value="Desafio de Conhecimento")
    n_prof = st.text_input("Professor(a)")
    q_itens = st.number_input("Quantidade", min_value=1, max_value=50, value=5)
    
    arquivos = st.file_uploader("Ficheiros", type=["pdf", "docx", "pptx", "png", "jpg", "jpeg"], accept_multiple_files=True)

    if arquivos and st.button(f"Gerar {tipo_conteudo}", use_container_width=True):
        if verificar_seguranca(arquivos):
            with st.spinner("A otimizar imagens e a gerar conteúdo..."):
                try:
                    txt = "".join([processar_arquivo(a)+"\n" for a in arquivos])
                    dados = gerar_dados_ia(txt, q_itens, tipo_conteudo)
                    
                    html_final = construir_html_jogo(dados, t_titulo, n_prof) if tipo_conteudo == "Quiz" else construir_html_flash(dados, t_titulo, n_prof)
                    
                    st.session_state["conteudo_pronto"] = html_final
                    st.session_state["link_conteudo"] = fazer_upload_firebase(html_final, tipo_conteudo.lower())
                    st.session_state["ultimo_uso"] = time.time()
                except Exception as e:
                    st.error(f"Erro na geração: {e}")

    if st.session_state.get("conteudo_pronto"):
        st.markdown("---")
        if st.session_state.get("link_conteudo"):
            st.info("📱 LINK DIRETO:")
            st.code(st.session_state["link_conteudo"], language="text")

        st.download_button(
            label="📥 Descarregar HTML",
            data=st.session_state["conteudo_pronto"],
            file_name="conteudo.html",
            mime="text/html",
            use_container_width=True
        )
        components.html(st.session_state["conteudo_pronto"], height=750, scrolling=True)
