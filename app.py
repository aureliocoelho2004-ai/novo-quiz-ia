"""Quizify - transforma PDFs, Word, PowerPoint e fotos em quizzes/flashcards com IA.

Toda a lógica fica aqui; o HTML vive em templates/ e o JS/CSS da página em static/.
"""
import io
import json
import logging
import os
import re
import unicodedata
import uuid

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge

log = logging.getLogger("quizify")
logging.basicConfig(level=logging.INFO)

MAX_ARQUIVOS = 5
MAX_TOTAL_MB = 50
MIN_ITENS, MAX_ITENS = 5, 50
MAX_CARACTERES_TEXTO = 60_000
EXTENSOES_DOC = {".pdf", ".docx", ".pptx"}
EXTENSOES_IMG = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
MIME_IMG = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_TOTAL_MB * 1024 * 1024
app.json.ensure_ascii = False


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
@app.get("/")
def index():
    return render_template("index.html", max_arquivos=MAX_ARQUIVOS, max_mb=MAX_TOTAL_MB,
                           min_itens=MIN_ITENS, max_itens=MAX_ITENS)


@app.get("/health")
def health():
    """Rota leve para o cron-job manter o serviço acordado no Render."""
    return "ok", 200


@app.post("/api/gerar")
def gerar():
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

    return jsonify(html=conteudo_html, link=link, total=len(itens),
                   nome_arquivo=f"{nome_seguro(titulo)}.html")


@app.errorhandler(RequestEntityTooLarge)
def arquivo_grande(_):
    return jsonify(erro=f"O tamanho total dos arquivos excede {MAX_TOTAL_MB} MB."), 413


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
