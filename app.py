"""Quizify - transforma PDFs, Word, PowerPoint e fotos em quizzes/flashcards com IA.

Toda a lógica fica aqui; o HTML vive em templates/ e o JS/CSS da página em static/.
"""
import hashlib
import io
import json
import logging
import os
import re
import unicodedata
import time
import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash

log = logging.getLogger("quizify")
logging.basicConfig(level=logging.INFO)

MAX_ARQUIVOS = 5
MAX_TOTAL_MB = 50
MIN_ITENS, MAX_ITENS = 5, 50
MAX_CARACTERES_TEXTO = 60_000
LIMITE_DIARIO = int(os.environ.get("LIMITE_DIARIO", 50))           # gerações por utilizador por dia
INTERVALO_SEGUNDOS = int(os.environ.get("INTERVALO_SEGUNDOS", 30))  # espera entre gerações
FUSO_BRASIL = timezone(timedelta(hours=-3))
EXTENSOES_DOC = {".pdf", ".docx", ".pptx"}
EXTENSOES_IMG = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MIME_IMG = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_TOTAL_MB * 1024 * 1024
app.json.ensure_ascii = False
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.environ.get("RENDER")),  # Render serve sempre por HTTPS
    PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 7,
)


def _chave_secreta():
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    # Sem SECRET_KEY, deriva uma chave estável de um segredo existente para que
    # todos os workers do gunicorn aceitem a mesma sessão.
    base = os.environ.get("FIREBASE_KEY") or os.environ.get("GEMINI_API_KEY")
    if base:
        log.warning("SECRET_KEY não definida; usando chave derivada. Defina SECRET_KEY no Render.")
        return hashlib.sha256(("quizify-sessao:" + base).encode()).hexdigest()
    log.warning("SECRET_KEY não definida; sessões serão perdidas ao reiniciar.")
    return os.urandom(32).hex()


app.secret_key = _chave_secreta()


# --------------------------------------------------------------------------- #
# Serviços externos (inicializados sob demanda para o app subir mesmo sem
# credenciais e o /health continuar a responder ao cron-job).
# --------------------------------------------------------------------------- #
_cliente_gemini = None
_bucket = None


def obter_segredo(chave):
    valor = os.environ.get(chave)
    if not valor:
        raise RuntimeError(f"Variável de ambiente ausente: {chave}")
    return valor


def gemini():
    global _cliente_gemini
    if _cliente_gemini is None:
        from google import genai
        _cliente_gemini = genai.Client(api_key=obter_segredo("GEMINI_API_KEY"))
    return _cliente_gemini


def bucket_firebase():
    global _bucket
    if _bucket is None:
        import firebase_admin
        from firebase_admin import credentials, storage
        if not firebase_admin._apps:
            cred = credentials.Certificate(json.loads(obter_segredo("FIREBASE_KEY")))
            firebase_admin.initialize_app(cred, {"storageBucket": obter_segredo("FIREBASE_BUCKET")})
        _bucket = storage.bucket()
    return _bucket


# --------------------------------------------------------------------------- #
# Utilizadores e autenticação
# Guardados em usuarios.json no Firebase, com senhas em hash:
#   {"nome": {"senha": "<hash>", "admin": bool, "trocar_senha": bool}}
# --------------------------------------------------------------------------- #
ARQUIVO_USUARIOS = "usuarios.json"
MAX_TENTATIVAS, JANELA_TENTATIVAS = 5, 10 * 60
_tentativas = {}


class FalhaUsuarios(Exception):
    """Não foi possível ler a lista de utilizadores do Firebase."""


def carregar_usuarios(estrito=False):
    """Com estrito=True, uma falha de leitura levanta FalhaUsuarios em vez de
    devolver uma lista vazia — obrigatório antes de gravar, senão a gravação
    apagaria todos os utilizadores existentes."""
    try:
        blob = bucket_firebase().blob(ARQUIVO_USUARIOS)
        dados = json.loads(blob.download_as_bytes()) if blob.exists() else {}
    except Exception as erro:
        log.exception("Falha ao ler utilizadores do Firebase")
        if estrito:
            raise FalhaUsuarios from erro
        dados = {}

    usuarios = {}
    for nome, valor in dados.items():
        if isinstance(valor, str):  # formato antigo (Streamlit): senha em texto puro
            valor = {"senha": generate_password_hash(valor), "admin": nome == "admin", "trocar_senha": True}
        usuarios[nome] = valor

    # Primeiro acesso: cria o admin a partir das variáveis de ambiente.
    if not usuarios and os.environ.get("ADMIN_PASSWORD"):
        nome = os.environ.get("ADMIN_USER", "admin").strip().lower()
        usuarios[nome] = {"senha": generate_password_hash(os.environ["ADMIN_PASSWORD"]),
                          "admin": True, "trocar_senha": False}
    return usuarios


def salvar_usuarios(usuarios):
    bucket_firebase().blob(ARQUIVO_USUARIOS).upload_from_string(
        json.dumps(usuarios, ensure_ascii=False), content_type="application/json")


def ip_cliente():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()


def bloqueado(ip):
    agora = time.time()
    _tentativas[ip] = [t for t in _tentativas.get(ip, []) if agora - t < JANELA_TENTATIVAS]
    return len(_tentativas[ip]) >= MAX_TENTATIVAS


def senha_valida(senha):
    return len(senha) >= 8


def conta_ainda_existe(usuarios):
    """Encerra a sessão se o utilizador foi removido depois de fazer login."""
    if session.get("usuario") in usuarios:
        return True
    session.clear()
    return False


def _blob_uso(usuario):
    return bucket_firebase().blob(f"uso/{usuario}.json")


def verificar_limite(usuario):
    """Devolve uma mensagem de erro se o utilizador passou do limite, senão None.
    Guardado no Firebase para valer entre workers e reinícios do Render.
    Administradores não têm limite."""
    hoje = datetime.now(FUSO_BRASIL).date().isoformat()
    try:
        blob = _blob_uso(usuario)
        uso = json.loads(blob.download_as_bytes()) if blob.exists() else {}
    except Exception:
        log.exception("Falha ao ler uso de %s", usuario)
        return None  # não bloqueia o professor por uma falha de leitura
    if uso.get("dia") != hoje:
        uso = {"dia": hoje, "total": 0, "ultimo": 0}

    espera = INTERVALO_SEGUNDOS - (time.time() - uso.get("ultimo", 0))
    if espera > 0:
        return f"⏳ Aguarde {int(espera) + 1}s para criar outro conteúdo."
    if uso["total"] >= LIMITE_DIARIO:
        return f"⚠️ Limite de {LIMITE_DIARIO} conteúdos por dia atingido. Tente novamente amanhã."

    uso["ultimo"] = time.time()  # marca já, para impedir pedidos simultâneos
    _gravar_uso(usuario, uso)
    return None


def registrar_geracao(usuario):
    hoje = datetime.now(FUSO_BRASIL).date().isoformat()
    try:
        blob = _blob_uso(usuario)
        uso = json.loads(blob.download_as_bytes()) if blob.exists() else {}
    except Exception:
        log.exception("Falha ao ler uso de %s", usuario)
        return
    if uso.get("dia") != hoje:
        uso = {"dia": hoje, "total": 0, "ultimo": time.time()}
    uso["total"] = uso.get("total", 0) + 1
    _gravar_uso(usuario, uso)


def _gravar_uso(usuario, uso):
    try:
        _blob_uso(usuario).upload_from_string(json.dumps(uso), content_type="application/json")
    except Exception:
        log.exception("Falha ao gravar uso de %s", usuario)


def login_obrigatorio(view):
    @wraps(view)
    def envolvida(*args, **kwargs):
        if not session.get("usuario"):
            if request.path.startswith("/api/"):
                return jsonify(erro="Sessão expirada. Entre novamente."), 401
            return redirect(url_for("login", proximo=request.path))
        if session.get("trocar_senha") and request.endpoint not in ("trocar_senha", "logout"):
            return redirect(url_for("trocar_senha"))
        return view(*args, **kwargs)
    return envolvida


def admin_obrigatorio(view):
    @wraps(view)
    @login_obrigatorio
    def envolvida(*args, **kwargs):
        if not session.get("admin"):
            abort(403)
        return view(*args, **kwargs)
    return envolvida


# --------------------------------------------------------------------------- #
# Extração de conteúdo
# --------------------------------------------------------------------------- #
def extensao(nome):
    return os.path.splitext(nome or "")[1].lower()


def extrair_pdf(dados):
    from pypdf import PdfReader
    leitor = PdfReader(io.BytesIO(dados))
    return "\n".join(t for p in leitor.pages if (t := p.extract_text()))


def extrair_docx(dados):
    import docx
    documento = docx.Document(io.BytesIO(dados))
    linhas = [p.text for p in documento.paragraphs if p.text.strip()]
    for tabela in documento.tables:
        for linha in tabela.rows:
            linhas.append(" | ".join(c.text.strip() for c in linha.cells if c.text.strip()))
    return "\n".join(linhas)


def extrair_pptx(dados):
    import pptx
    linhas = []
    for slide in pptx.Presentation(io.BytesIO(dados)).slides:
        for forma in slide.shapes:
            if forma.has_text_frame:
                linhas.extend(p.text.strip() for p in forma.text_frame.paragraphs if p.text.strip())
    return "\n".join(linhas)


def reduzir_imagem(dados, mime):
    """Rede de segurança: o navegador já comprime, mas imagens grandes que
    escaparem (ex.: HEIC que o navegador não lê) são reduzidas aqui."""
    if len(dados) <= 1_500_000:
        return dados, mime
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(dados))
        img.thumbnail((1600, 1600))
        saida = io.BytesIO()
        img.convert("RGB").save(saida, "JPEG", quality=80)
        return saida.getvalue(), "image/jpeg"
    except Exception:
        return dados, mime


def preparar_conteudo(arquivos):
    """Devolve (texto_extraido, partes_binarias) para enviar ao Gemini numa só chamada."""
    from google.genai import types

    textos, partes = [], []
    for arq in arquivos:
        ext = extensao(arq.filename)
        dados = arq.read()
        if not dados:
            continue
        if ext == ".pdf":
            texto = extrair_pdf(dados)
            if texto.strip():
                textos.append(texto)
            else:  # PDF digitalizado (só imagens): o Gemini lê o PDF diretamente
                partes.append(types.Part.from_bytes(data=dados, mime_type="application/pdf"))
        elif ext == ".docx":
            textos.append(extrair_docx(dados))
        elif ext == ".pptx":
            textos.append(extrair_pptx(dados))
        elif ext in EXTENSOES_IMG or (arq.mimetype or "").startswith("image/"):
            dados, mime = reduzir_imagem(dados, arq.mimetype or MIME_IMG.get(ext, "image/jpeg"))
            partes.append(types.Part.from_bytes(data=dados, mime_type=mime))
    return "\n\n".join(t for t in textos if t.strip())[:MAX_CARACTERES_TEXTO], partes


# --------------------------------------------------------------------------- #
# Geração com IA
# --------------------------------------------------------------------------- #
PROMPT_QUIZ = """Você é um professor experiente. Com base EXCLUSIVAMENTE no material fornecido
(texto e/ou imagens), crie {n} perguntas de múltipla escolha em português do Brasil.
Regras:
- Cada pergunta tem exatamente 4 opções, apenas UMA correta.
- Varie a posição da resposta correta.
- "correta" é o ÍNDICE (0 a 3) da opção correta.
- "explicacao" justifica a resposta em 1 ou 2 frases.
Responda apenas com um array JSON no formato:
[{{"pergunta": "...", "opcoes": ["...", "...", "...", "..."], "correta": 0, "explicacao": "..."}}]"""

PROMPT_FLASH = """Você é um professor experiente. Com base EXCLUSIVAMENTE no material fornecido
(texto e/ou imagens), crie {n} flashcards em português do Brasil com os conceitos mais importantes.
Responda apenas com um array JSON no formato:
[{{"frente": "conceito ou pergunta curta", "verso": "explicação ou resposta"}}]"""


def chamar_gemini(prompt, texto, partes):
    from google.genai import types

    conteudo = [prompt]
    if texto:
        conteudo.append(f"MATERIAL:\n{texto}")
    conteudo.extend(partes)
    resposta = gemini().models.generate_content(
        model=os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
        contents=conteudo,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.4),
    )
    bruto = re.sub(r"^```(?:json)?\s*|\s*```$", "", (resposta.text or "").strip())
    dados = json.loads(bruto)
    if isinstance(dados, dict):  # às vezes vem embrulhado: {"perguntas": [...]}
        dados = next((v for v in dados.values() if isinstance(v, list)), [])
    return dados


def normalizar_quiz(itens, n):
    quiz = []
    for item in itens:
        opcoes = [str(o).strip() for o in item.get("opcoes", []) if str(o).strip()]
        try:
            correta = int(item.get("correta", item.get("resposta_correta", -1)))
        except (TypeError, ValueError):
            continue
        if not item.get("pergunta") or len(opcoes) < 2 or not 0 <= correta < len(opcoes):
            continue
        quiz.append({"id": len(quiz), "pergunta": str(item["pergunta"]).strip(), "opcoes": opcoes,
                     "correta": correta, "explicacao": str(item.get("explicacao", "")).strip()})
    return quiz[:n]


def normalizar_flash(itens, n):
    return [{"frente": str(i["frente"]).strip(), "verso": str(i["verso"]).strip()}
            for i in itens if i.get("frente") and i.get("verso")][:n]


# --------------------------------------------------------------------------- #
# Publicação
# --------------------------------------------------------------------------- #
def nome_seguro(texto):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()[:40] or "quizify"


def publicar_firebase(conteudo_html, prefixo):
    try:
        blob = bucket_firebase().blob(f"quizzes/{prefixo}_{uuid.uuid4().hex[:10]}.html")
        blob.cache_control = "public, max-age=3600"
        # charset explícito: sem ele acentos/emojis aparecem corrompidos no Android/iOS
        blob.upload_from_string(conteudo_html.encode("utf-8"), content_type="text/html; charset=utf-8")
        blob.make_public()
        return blob.public_url
    except Exception:
        log.exception("Falha ao publicar no Firebase")
        return None


# --------------------------------------------------------------------------- #
# Rotas
# --------------------------------------------------------------------------- #
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    ip = ip_cliente()
    if bloqueado(ip):
        flash("Muitas tentativas. Aguarde alguns minutos e tente novamente.", "erro")
        return render_template("login.html"), 429

    nome = request.form.get("usuario", "").strip().lower()
    senha = request.form.get("senha", "")
    usuarios = carregar_usuarios()
    conta = usuarios.get(nome)
    if not conta or not check_password_hash(conta["senha"], senha):
        _tentativas[ip].append(time.time())
        flash("Utilizador ou senha incorretos.", "erro")
        return render_template("login.html", usuario=nome), 401

    _tentativas.pop(ip, None)
    session.clear()
    session.permanent = True
    session.update(usuario=nome, admin=bool(conta.get("admin")), trocar_senha=bool(conta.get("trocar_senha")))
    proximo = request.args.get("proximo", "")
    return redirect(proximo if proximo.startswith("/") and not proximo.startswith("//") else url_for("index"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/trocar-senha", methods=["GET", "POST"])
@login_obrigatorio
def trocar_senha():
    if request.method == "POST":
        try:
            usuarios = carregar_usuarios(estrito=True)
        except FalhaUsuarios:
            flash("Serviço temporariamente indisponível. Tente novamente.", "erro")
            return render_template("trocar_senha.html", obrigatorio=session.get("trocar_senha")), 503
        if not conta_ainda_existe(usuarios):
            return redirect(url_for("login"))
        conta = usuarios[session["usuario"]]
        atual, nova = request.form.get("atual", ""), request.form.get("nova", "")
        if not conta or not check_password_hash(conta["senha"], atual):
            flash("Senha atual incorreta.", "erro")
        elif not senha_valida(nova):
            flash("A nova senha deve ter pelo menos 8 caracteres.", "erro")
        elif nova != request.form.get("confirmar", ""):
            flash("A confirmação não coincide com a nova senha.", "erro")
        elif nova == atual:
            flash("A nova senha deve ser diferente da atual.", "erro")
        else:
            conta.update(senha=generate_password_hash(nova), trocar_senha=False)
            try:
                salvar_usuarios(usuarios)
            except Exception:
                log.exception("Falha ao guardar utilizadores")
                flash("Não foi possível guardar a senha. Tente novamente.", "erro")
            else:
                session["trocar_senha"] = False
                flash("Senha alterada com sucesso.", "ok")
                return redirect(url_for("index"))
    return render_template("trocar_senha.html", obrigatorio=session.get("trocar_senha"))


@app.route("/admin", methods=["GET", "POST"])
@admin_obrigatorio
def admin():
    try:
        usuarios = carregar_usuarios(estrito=True)
    except FalhaUsuarios:
        flash("Não foi possível ler os utilizadores do Firebase. Tente novamente.", "erro")
        return render_template("admin.html", usuarios=[]), 503
    if not conta_ainda_existe(usuarios) or not usuarios[session["usuario"]].get("admin"):
        session.clear()
        return redirect(url_for("login"))
    if request.method == "POST":
        acao = request.form.get("acao")
        nome = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "")
        if acao == "criar":
            if not re.fullmatch(r"[a-z0-9._-]{3,30}", nome):
                flash("Nome inválido: use 3 a 30 letras minúsculas, números, ponto, hífen ou _.", "erro")
            elif nome in usuarios:
                flash(f"O utilizador '{nome}' já existe.", "erro")
            elif not senha_valida(senha):
                flash("A senha deve ter pelo menos 8 caracteres.", "erro")
            else:
                usuarios[nome] = {"senha": generate_password_hash(senha),
                                  "admin": request.form.get("admin") == "1", "trocar_senha": True}
                flash(f"Utilizador '{nome}' criado. Ele terá de trocar a senha no primeiro acesso.", "ok")
        elif acao == "redefinir" and nome in usuarios:
            if not senha_valida(senha):
                flash("A senha deve ter pelo menos 8 caracteres.", "erro")
            else:
                usuarios[nome].update(senha=generate_password_hash(senha), trocar_senha=True)
                flash(f"Senha de '{nome}' redefinida.", "ok")
        elif acao == "remover" and nome in usuarios:
            if nome == session["usuario"]:
                flash("Não pode remover a sua própria conta.", "erro")
            else:
                del usuarios[nome]
                flash(f"Utilizador '{nome}' removido.", "ok")
        else:
            abort(400)

        try:
            salvar_usuarios(usuarios)
        except Exception:
            log.exception("Falha ao guardar utilizadores")
            flash("Não foi possível guardar as alterações no Firebase.", "erro")
        return redirect(url_for("admin"))

    return render_template("admin.html", usuarios=sorted(usuarios.items()))


@app.get("/")
@login_obrigatorio
def index():
    return render_template("index.html", max_arquivos=MAX_ARQUIVOS, max_mb=MAX_TOTAL_MB,
                           min_itens=MIN_ITENS, max_itens=MAX_ITENS)


@app.get("/health")
def health():
    """Rota leve para o cron-job manter o serviço acordado no Render."""
    return "ok", 200


@app.post("/api/gerar")
@login_obrigatorio
def gerar():
    try:
        usuarios = carregar_usuarios(estrito=True)
    except FalhaUsuarios:
        return jsonify(erro="Serviço temporariamente indisponível. Tente novamente."), 503
    if not conta_ainda_existe(usuarios):
        return jsonify(erro="A sua conta já não está ativa. Entre novamente."), 401
    usuario = session["usuario"]
    sem_limite = bool(usuarios[usuario].get("admin"))

    arquivos = [a for a in request.files.getlist("arquivos") if a and a.filename]
    tipo = request.form.get("tipo", "quiz")
    titulo = (request.form.get("titulo") or "Desafio de Conhecimento").strip()[:120]
    professor = (request.form.get("professor") or "").strip()[:80]
    try:
        n = min(max(int(request.form.get("quantidade", 10)), MIN_ITENS), MAX_ITENS)
    except ValueError:
        n = 10

    if tipo not in ("quiz", "flashcards"):
        return jsonify(erro="Tipo inválido."), 400
    if not arquivos:
        return jsonify(erro="Envie pelo menos um arquivo ou foto."), 400
    if len(arquivos) > MAX_ARQUIVOS:
        return jsonify(erro=f"Envie no máximo {MAX_ARQUIVOS} arquivos de cada vez."), 400
    invalidos = [a.filename for a in arquivos
                 if extensao(a.filename) not in EXTENSOES_DOC | EXTENSOES_IMG
                 and not (a.mimetype or "").startswith("image/")]
    if invalidos:
        return jsonify(erro=f"Formato não suportado: {', '.join(invalidos)}"), 400
    if not sem_limite and (aviso := verificar_limite(usuario)):
        return jsonify(erro=aviso), 429

    try:
        texto, partes = preparar_conteudo(arquivos)
    except Exception:
        log.exception("Falha na extração")
        return jsonify(erro="Não foi possível ler um dos arquivos. Verifique se não está corrompido."), 422
    if not texto and not partes:
        return jsonify(erro="Não encontrei texto nos arquivos enviados."), 422

    try:
        if tipo == "quiz":
            itens = normalizar_quiz(chamar_gemini(PROMPT_QUIZ.format(n=n), texto, partes), n)
        else:
            itens = normalizar_flash(chamar_gemini(PROMPT_FLASH.format(n=n), texto, partes), n)
    except Exception:
        log.exception("Falha na geração com IA")
        return jsonify(erro="A IA não conseguiu gerar o conteúdo. Tente novamente."), 502
    if not itens:
        return jsonify(erro="A IA devolveu um resultado vazio. Tente novamente."), 502

    template = "quiz.html" if tipo == "quiz" else "flashcards.html"
    conteudo_html = render_template(template, titulo=titulo, professor=professor, itens=itens)
    link = publicar_firebase(conteudo_html, tipo)
    if not sem_limite:
        registrar_geracao(usuario)

    return jsonify(html=conteudo_html, link=link, total=len(itens),
                   nome_arquivo=f"{nome_seguro(titulo)}.html")


@app.errorhandler(RequestEntityTooLarge)
def arquivo_grande(_):
    return jsonify(erro=f"O tamanho total dos arquivos excede {MAX_TOTAL_MB} MB."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
