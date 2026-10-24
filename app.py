import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials, storage
from pypdf import PdfReader
import docx
import pptx
from PIL import Image
import hmac
import json
import re
import time
import html
import uuid
import os

st.set_page_config(page_title="Quizify", layout="centered")

LIMITE_CARACTERES = 50000          # texto enviado à IA
LIMITE_UPLOAD_MB = 200
INTERVALO_MIN_SEGUNDOS = 30


# ---------------------------------------------------------------------------
# Configuração / segredos
# ---------------------------------------------------------------------------
def obter_segredo(chave, padrao=None):
    if chave in os.environ:
        return os.environ[chave]
    try:
        return st.secrets[chave]
    except Exception:
        if padrao is not None:
            return padrao
        raise ValueError(f"Variável ausente: {chave}")


try:
    cliente_ia = genai.Client(api_key=obter_segredo("GEMINI_API_KEY"))
    # Modelo configurável: troque em secrets/env sem mexer no código.
    MODELO = obter_segredo("GEMINI_MODEL", "gemini-3.5-flash")

    if not firebase_admin._apps:
        cert_dict = json.loads(obter_segredo("FIREBASE_KEY"))
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {"storageBucket": obter_segredo("FIREBASE_BUCKET")})
except Exception as e:
    st.error(f"Erro de infraestrutura: {e}")
    st.stop()


def chamar_ia(conteudo, json_mode=False):
    config = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    resposta = cliente_ia.models.generate_content(model=MODELO, contents=conteudo, config=config)
    return resposta.text or ""


def fazer_upload_firebase(conteudo_html, prefixo="quizify"):
    """Devolve (url, erro). Antes o erro era engolido e o link simplesmente não aparecia."""
    try:
        nome_arquivo = f"{prefixo}_{uuid.uuid4().hex[:8]}.html"
        blob = storage.bucket().blob(nome_arquivo)
        blob.upload_from_string(conteudo_html.encode("utf-8"), content_type="text/html; charset=utf-8")
        # Falha se o bucket usa "uniform bucket-level access" (padrão em buckets novos).
        # Nesse caso, torne o bucket/pasta público nas permissões do Google Cloud.
        blob.make_public()
        return blob.public_url, None
    except Exception as e:
        return None, str(e)


st.markdown(
    "<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Usuários: o ideal é definir USUARIOS_JSON nos secrets, ex.:
#   USUARIOS_JSON = '{"professor": "senha-forte", "escola_demo": "outra-senha"}'
# O fallback abaixo mantém o comportamento antigo, mas é inseguro (senhas no código).
# ---------------------------------------------------------------------------
def carregar_usuarios():
    try:
        return json.loads(obter_segredo("USUARIOS_JSON"))
    except Exception:
        usuarios = {"admin": "admin123", "escola_demo": "quiz2026", "professor": "aula123"}
        for i in range(1, 51):
            usuarios[f"beta{i}"] = f"beta{i}"
        return usuarios


USUARIOS_AUTORIZADOS = carregar_usuarios()

for chave, valor in {
    "autenticado": False,
    "ultimo_uso": 0.0,
    "conteudo_pronto": None,
    "link_conteudo": None,
}.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


def verificar_seguranca(arquivos):
    """Devolve uma mensagem de erro ou None. Antes retornava False sem avisar nada ao usuário."""
    if sum(arq.size for arq in arquivos) > LIMITE_UPLOAD_MB * 1024 * 1024:
        return f"Os ficheiros somam mais de {LIMITE_UPLOAD_MB} MB."
    restante = INTERVALO_MIN_SEGUNDOS - (time.time() - st.session_state["ultimo_uso"])
    if restante > 0:
        return f"Aguarde {int(restante) + 1} segundos antes de gerar novamente."
    return None


# ---------------------------------------------------------------------------
# Leitura dos ficheiros
# ---------------------------------------------------------------------------
def processar_arquivo(a):
    n = a.name.lower()
    a.seek(0)
    if n.endswith(".pdf"):
        textos = []
        for p in PdfReader(a).pages:
            t = p.extract_text()  # extrai uma vez só (antes eram duas por página)
            if t:
                textos.append(t)
        return "\n".join(textos)
    if n.endswith(".docx"):
        return "\n".join(p.text for p in docx.Document(a).paragraphs if p.text.strip())
    if n.endswith(".pptx"):
        t = []
        for s in pptx.Presentation(a).slides:
            for sh in s.shapes:
                if sh.has_text_frame:
                    t.extend(p.text.strip() for p in sh.text_frame.paragraphs if p.text.strip())
        return "\n".join(t)
    if n.endswith((".png", ".jpg", ".jpeg")):
        try:
            return chamar_ia([Image.open(a), "Transcreva todo o texto visível nesta imagem."])
        except Exception as e:
            st.warning(f"Não foi possível ler a imagem {a.name}: {e}")
            return ""
    return ""


# ---------------------------------------------------------------------------
# Geração e validação dos dados
# ---------------------------------------------------------------------------
def extrair_json(texto):
    texto = re.sub(r"```(?:json)?", "", texto).strip()
    dados = json.loads(texto)
    # Às vezes o modelo devolve {"perguntas": [...]} em vez da lista direta
    if isinstance(dados, dict):
        listas = [v for v in dados.values() if isinstance(v, list)]
        dados = listas[0] if listas else []
    if not isinstance(dados, list):
        raise ValueError("A IA não devolveu uma lista.")
    return dados


def validar_quiz(dados, quantidade):
    letras = "ABCDEFGH"
    validos = []
    for item in dados:
        if not isinstance(item, dict):
            continue
        pergunta = str(item.get("pergunta", "")).strip()
        opcoes = item.get("opcoes")
        rc = item.get("resposta_correta")
        if not pergunta or not isinstance(opcoes, list) or len(opcoes) < 2:
            continue
        opcoes = [str(o) for o in opcoes]
        if isinstance(rc, str):
            r = rc.strip()
            if r.isdigit():
                rc = int(r)
            elif len(r) == 1 and r.upper() in letras:
                rc = letras.index(r.upper())
            elif r in opcoes:
                rc = opcoes.index(r)
            else:
                continue
        if isinstance(rc, bool) or not isinstance(rc, int) or not 0 <= rc < len(opcoes):
            continue
        validos.append({
            "pergunta": pergunta,
            "opcoes": opcoes,
            "resposta_correta": rc,
            "explicacao": str(item.get("explicacao", "")).strip(),
        })
    return validos[:quantidade]


def validar_flash(dados, quantidade):
    validos = []
    for item in dados:
        if isinstance(item, dict):
            frente = str(item.get("frente", "")).strip()
            verso = str(item.get("verso", "")).strip()
            if frente and verso:
                validos.append({"frente": frente, "verso": verso})
    return validos[:quantidade]


def gerar_dados_ia(texto_base, quantidade, tipo_conteudo):
    texto = texto_base[:LIMITE_CARACTERES]
    if tipo_conteudo == "Quiz":
        prompt = (
            f"Crie um quiz de múltipla escolha com exatamente {quantidade} perguntas, em português, "
            "baseado SOMENTE no texto abaixo. Cada pergunta deve ter 4 opções de resposta completas "
            "(o texto da alternativa, não apenas letras). "
            "Retorne APENAS um array JSON neste formato: "
            '[{"pergunta": "...", "opcoes": ["...", "...", "...", "..."], '
            '"resposta_correta": 0, "explicacao": "..."}]. '
            '"resposta_correta" é o ÍNDICE da opção correta, começando em 0 (0 = primeira opção). '
            "Varie a posição da resposta correta entre as perguntas.\n\nTEXTO:\n" + texto
        )
    else:
        prompt = (
            f"Crie exatamente {quantidade} flashcards em português, baseados SOMENTE no texto abaixo. "
            'Retorne APENAS um array JSON neste formato: [{"frente": "...", "verso": "..."}].'
            "\n\nTEXTO:\n" + texto
        )
    dados = extrair_json(chamar_ia(prompt, json_mode=True))
    dados = validar_quiz(dados, quantidade) if tipo_conteudo == "Quiz" else validar_flash(dados, quantidade)
    if not dados:
        raise ValueError("A IA não devolveu itens válidos. Tente novamente.")
    return dados


# ---------------------------------------------------------------------------
# HTML gerado
# ---------------------------------------------------------------------------
def json_para_script(dados):
    # Impede que um "</script>" dentro do conteúdo quebre a página
    return json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")


def cabecalho_html(titulo, professor, estilos):
    linha_prof = (
        f"<p class='text-center text-slate-400 text-sm mb-4 pb-4 border-b border-slate-700 w-full'>Prof. {html.escape(professor)}</p>"
        if professor.strip()
        else "<div class='mb-4 pb-4 border-b border-slate-700 w-full'></div>"
    )
    return (
        "<!DOCTYPE html><html lang='pt'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
        f"<title>{html.escape(titulo)}</title><script src='https://cdn.tailwindcss.com'></script>"
        f"<style>{estilos}</style></head>"
        "<body class='bg-slate-900 text-white flex items-center justify-center min-h-screen p-4'>"
        "<div class='w-full max-w-md bg-slate-800 rounded-2xl p-6 border border-slate-700 flex flex-col'>"
        f"<h1 class='text-2xl font-extrabold text-center text-indigo-400 mb-1'>{html.escape(titulo)}</h1>"
        + linha_prof
    )


JS_QUIZ = """
const pergs = __DADOS__;
let ind = 0, acertos = 0, resp = false;
const el = id => document.getElementById(id);

function carregar() {
  resp = false;
  const p = pergs[ind];
  el('prog').textContent = `Pergunta ${ind + 1} de ${pergs.length}`;
  el('t-perg').textContent = p.pergunta;
  el('tela-f').className = 'hidden mt-6 p-4 rounded-xl text-center';
  const c = el('opc');
  c.innerHTML = '';
  p.opcoes.forEach((o, i) => {
    const b = document.createElement('button');
    b.textContent = o;
    b.className = 'w-full bg-slate-700 border-2 border-slate-600 text-left py-3 px-5 rounded-xl text-white font-bold text-lg';
    b.onclick = () => verificar(i, b);
    c.appendChild(b);
  });
}

function verificar(iS, b) {
  if (resp) return;
  resp = true;
  const p = pergs[ind];
  const botoes = Array.from(el('opc').children);
  botoes.forEach(x => { x.disabled = true; });
  botoes[p.resposta_correta].classList.add('correto');
  const tf = el('tela-f');
  const txt = el('f-txt');
  txt.textContent = '';
  if (iS === p.resposta_correta) {
    acertos++;
    tf.className = 'mt-6 p-4 rounded-xl text-center bg-green-900';
    el('f-tit').textContent = '✅ Correto!';
  } else {
    b.classList.add('errado');
    tf.className = 'mt-6 p-4 rounded-xl text-center bg-red-900';
    el('f-tit').textContent = '❌ Incorreto!';
    const certa = document.createElement('p');
    certa.className = 'mb-2';
    certa.append('A resposta certa é: ');
    const negrito = document.createElement('b');
    negrito.textContent = p.opcoes[p.resposta_correta];
    certa.append(negrito);
    txt.append(certa);
  }
  if (p.explicacao) {
    const exp = document.createElement('p');
    exp.textContent = p.explicacao;
    txt.append(exp);
  }
  el('btn-prox').textContent = ind + 1 < pergs.length ? 'Continuar' : 'Ver resultado';
}

function prox() { ind++; if (ind < pergs.length) carregar(); else mostrar(); }

function mostrar() {
  el('tela-p').classList.add('hidden');
  el('tela-r').classList.remove('hidden');
  el('p-fin').textContent = `${acertos} de ${pergs.length} (${Math.round(acertos / pergs.length * 100)}%)`;
}

carregar();
"""


def construir_html_jogo(json_dados, titulo, professor):
    estilos = ".correto{background-color:#22c55e!important;color:white!important;}" \
              ".errado{background-color:#ef4444!important;color:white!important;}"
    return (
        cabecalho_html(titulo, professor, estilos)
        + "<div id='tela-p'>"
        "<p id='prog' class='text-slate-400 text-sm text-center mb-2'></p>"
        "<h2 id='t-perg' class='text-xl font-bold mb-4 text-center'>A carregar...</h2>"
        "<div id='opc' class='flex flex-col gap-3'></div>"
        "<div id='tela-f' class='hidden mt-6 p-4 rounded-xl text-center'>"
        "<h3 id='f-tit' class='font-bold text-lg mb-2'></h3><div id='f-txt' class='text-sm'></div>"
        "<button id='btn-prox' onclick='prox()' class='mt-4 w-full bg-indigo-600 py-3 rounded-xl font-bold'>Continuar</button>"
        "</div></div>"
        "<div id='tela-r' class='hidden text-center'><div class='text-6xl mb-4'>🏆</div>"
        "<h2 class='text-2xl font-bold mb-2'>Fim!</h2>"
        "<p>Acertou <span id='p-fin' class='font-bold text-indigo-400 text-2xl'></span></p>"
        "<button onclick='location.reload()' class='mt-6 w-full bg-indigo-600 py-3 rounded-xl font-bold'>Jogar novamente</button>"
        "</div></div>"
        "<script>" + JS_QUIZ.replace("__DADOS__", json_para_script(json_dados)) + "</script></body></html>"
    )


JS_FLASH = """
const cards = __DADOS__;
let ind = 0;
const el = id => document.getElementById(id);
el('t').textContent = cards.length;

function carregar() {
  el('card').classList.remove('flipped');
  setTimeout(() => {
    el('fr').textContent = cards[ind].frente;
    el('bk').textContent = cards[ind].verso;
    el('c').textContent = ind + 1;
    el('ant').disabled = ind === 0;
    el('prx').disabled = ind === cards.length - 1;
  }, 150);
}
function virar() { el('card').classList.toggle('flipped'); }
function mudar(dir) {
  const novo = ind + dir;
  if (novo >= 0 && novo < cards.length) { ind = novo; carregar(); }
}
carregar();
"""


def construir_html_flash(json_dados, titulo, professor):
    estilos = (
        ".pers{perspective:1000px;}"
        ".flip-in{transition:transform 0.6s;transform-style:preserve-3d;position:relative;width:100%;height:100%;}"
        ".flipped .flip-in{transform:rotateY(180deg);}"
        ".f-front,.f-back{-webkit-backface-visibility:hidden;backface-visibility:hidden;position:absolute;inset:0;"
        "display:flex;align-items:center;justify-content:center;padding:2rem;text-align:center;"
        "border-radius:1rem;overflow-y:auto;}"
        ".f-front{background-color:#334155;border:2px solid #475569;}"
        ".f-back{transform:rotateY(180deg);background-color:#4f46e5;}"
        "button:disabled{opacity:.4;cursor:not-allowed;}"
    )
    return (
        cabecalho_html(titulo, professor, estilos)
        + "<p class='text-slate-400 mb-2 text-sm text-center'>Cartão <span id='c'>1</span> de <span id='t'></span> · toque para virar</p>"
        "<div id='card' class='pers w-full h-64 mb-6 cursor-pointer' onclick='virar()'>"
        "<div class='flip-in rounded-2xl shadow-xl'>"
        "<div class='f-front'><h2 id='fr' class='text-xl font-bold'></h2></div>"
        "<div class='f-back'><p id='bk' class='text-lg font-medium'></p></div>"
        "</div></div>"
        "<div class='flex justify-between w-full gap-4'>"
        "<button id='ant' onclick='mudar(-1)' class='flex-1 bg-slate-700 py-3 rounded-xl font-bold'>Anterior</button>"
        "<button id='prx' onclick='mudar(1)' class='flex-1 bg-indigo-600 py-3 rounded-xl font-bold'>Próximo</button>"
        "</div></div>"
        "<script>" + JS_FLASH.replace("__DADOS__", json_para_script(json_dados)) + "</script></body></html>"
    )


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
if not st.session_state["autenticado"]:
    st.markdown("<h2 style='text-align: center;'>🔐 Acesso Restrito</h2>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("form_login"):
            usuario = st.text_input("Utilizador").strip().lower()
            senha = st.text_input("Palavra-passe", type="password").strip()
            if st.form_submit_button("Entrar", use_container_width=True):
                senha_certa = USUARIOS_AUTORIZADOS.get(usuario)
                if senha_certa is not None and hmac.compare_digest(str(senha_certa), senha):
                    st.session_state["autenticado"] = True
                    st.rerun()
                else:
                    st.error("Acesso negado.")
else:
    st.title("🎲 Quizify")
    tipo_conteudo = st.radio("Criar:", ["Quiz", "Flashcards"], horizontal=True)
    t_titulo = st.text_input("Título", value="Desafio de Conhecimento")
    n_prof = st.text_input("Professor(a)")
    q_itens = int(st.number_input("Quantidade", min_value=1, max_value=50, value=5))
    arquivos = st.file_uploader(
        "Ficheiros", type=["pdf", "docx", "pptx", "png", "jpg", "jpeg"], accept_multiple_files=True
    )

    if arquivos and st.button(f"Gerar {tipo_conteudo}", use_container_width=True):
        erro = verificar_seguranca(arquivos)
        if erro:
            st.warning(erro)
        else:
            with st.spinner("Processando na nuvem..."):
                try:
                    txt = "\n".join(processar_arquivo(a) for a in arquivos)
                    if not txt.strip():
                        st.error("Não foi possível extrair texto dos ficheiros (PDF digitalizado como imagem?).")
                    else:
                        dados = gerar_dados_ia(txt, q_itens, tipo_conteudo)
                        if tipo_conteudo == "Quiz":
                            html_final = construir_html_jogo(dados, t_titulo, n_prof)
                        else:
                            html_final = construir_html_flash(dados, t_titulo, n_prof)

                        st.session_state["conteudo_pronto"] = html_final
                        link, erro_up = fazer_upload_firebase(html_final, tipo_conteudo.lower())
                        st.session_state["link_conteudo"] = link
                        if erro_up:
                            st.warning(f"Conteúdo gerado, mas o link público falhou: {erro_up}")
                        if len(dados) < q_itens:
                            st.info(f"A IA gerou {len(dados)} de {q_itens} itens válidos.")
                        st.session_state["ultimo_uso"] = time.time()
                except json.JSONDecodeError:
                    st.error("A IA devolveu uma resposta em formato inválido. Tente novamente.")
                except Exception as e:
                    st.error(f"Erro na geração: {e}")

    if st.session_state.get("conteudo_pronto"):
        st.markdown("---")
        if st.session_state.get("link_conteudo"):
            st.info("📱 LINK DIRETO:")
            st.code(st.session_state["link_conteudo"], language="text")

        nome_seguro = re.sub(r"[^\w\-]+", "_", t_titulo.strip()).strip("_") or "conteudo"
        st.download_button(
            label="📥 Descarregar HTML",
            data=st.session_state["conteudo_pronto"],
            file_name=f"{nome_seguro}.html",
            mime="text/html",
            use_container_width=True,
        )
        components.html(st.session_state["conteudo_pronto"], height=750, scrolling=True)
