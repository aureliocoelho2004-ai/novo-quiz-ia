import streamlit as st
import PyPDF2
import time
from PIL import Image
import pytesseract
import google.generativeai as genai
import json

# Configuração da página
st.set_page_config(page_title="Quizify - Aprenda a Jogar", page_icon="🧩", layout="centered")

# Barra Lateral para configurações de IA
with st.sidebar:
    st.header("⚙️ Configuração da IA")
    st.write("Insira a sua chave API do Google Gemini para ativar o cérebro do Quizify.")
    api_key = st.text_input("Chave API do Gemini:", type="password")
    if api_key:
        genai.configure(api_key=api_key)
        st.success("API Key configurada para esta sessão!")
    st.markdown("---")
    st.write("As suas chaves não são guardadas e desaparecem ao fechar a aplicação.")

st.title("🧩 Quizify")
st.markdown("### Transforme qualquer material num jogo interativo")
st.write("Crie quizzes e flashcards a partir de PDFs ou Imagens para os seus alunos, filhos ou para o seu próprio estudo.")

# 1. Memória da aplicação
if "material_processado" not in st.session_state:
    st.session_state.material_processado = False
if "texto_extraido" not in st.session_state:
    st.session_state.texto_extraido = ""

# 2. Área de Upload e Câmara
st.markdown("---")
st.subheader("1. Envie o material base")

aba_arquivo, aba_camera = st.tabs(["📁 Enviar Arquivo", "📷 Tirar Foto na Hora"])
arquivo = None

with aba_arquivo:
    arquivo_upload = st.file_uploader("Faça o upload do documento (PDF, PNG, JPG, JPEG)", type=["pdf", "png", "jpg", "jpeg"])
    if arquivo_upload is not None:
        arquivo = arquivo_upload

with aba_camera:
    foto_tirada = st.camera_input("Tire uma foto do caderno, quadro ou livro")
    if foto_tirada is not None:
        arquivo = foto_tirada

# 3. Lógica de processamento (Extração de Texto)
if arquivo is not None:
    if st.button("Analisar Documento", type="primary"):
        with st.spinner("A extrair informações do documento..."):
            try:
                texto = ""
                if arquivo.name.lower().endswith('.pdf'):
                    leitor_pdf = PyPDF2.PdfReader(arquivo)
                    for pagina in leitor_pdf.pages:
                        texto_pagina = pagina.extract_text()
                        if texto_pagina:
                            texto += texto_pagina + "\n"
                elif arquivo.name.lower().endswith(('.png', '.jpg', '.jpeg')) or arquivo.type.startswith('image/'):
                    imagem = Image.open(arquivo)
                    try:
                        texto = pytesseract.image_to_string(imagem, lang='por')
                    except Exception:
                        texto = pytesseract.image_to_string(imagem)
                
                if not texto.strip():
                    st.error("⚠️ Não foi possível encontrar texto neste arquivo. Se for uma imagem, certifique-se de que está nítida.")
                else:
                    st.session_state.texto_extraido = texto
                    st.session_state.material_processado = True
                    time.sleep(0.5) 
                    st.success("✅ Texto extraído com sucesso!")
            except Exception as e:
                st.error(f"❌ Erro ao processar o arquivo: {e}")

# 4. Configuração e Geração via IA (Gemini)
if st.session_state.material_processado:
    st.markdown("---")
    st.subheader("2. Configure o seu Jogo")
    
    with st.expander("Ver texto extraído do documento"):
        st.write(st.session_state.texto_extraido[:1000] + ("..." if len(st.session_state.texto_extraido) > 1000 else ""))
    
    publico_alvo = st.selectbox(
        "Para quem é este jogo?", 
        ["Alunos (Ensino Fundamental)", "Alunos (Ensino Médio)", "Alunos (Ensino Superior)", "Estudantes para o ENEM", "Candidatos a Concursos Públicos", "Filhos (Estudo em Casa)", "Treinamento Corporativo / Geral"]
    )
    
    quantidade_perguntas = st.slider("Quantas perguntas deseja gerar?", min_value=5, max_value=50, value=5)
    
    if st.button("✨ Gerar Quizz e Flashcards"):
        if not api_key:
            st.warning("⚠️ Atenção: Por favor, cole a sua Chave API do Gemini no menu lateral esquerdo primeiro.")
        else:
            with st.spinner(f"A Inteligência Artificial (Gemini) está a criar {quantidade_perguntas} perguntas e flashcards..."):
                try:
                    # Configurar o modelo (Usando o Flash, que é rápido e barato)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    
                    # O "Prompt" (Instrução) que enviamos ao Gemini
                    prompt = f"""
                    Atue como um professor especialista em gamificação e elaboração de provas.
                    Com base no texto fornecido, crie um quiz de {quantidade_perguntas} perguntas de múltipla escolha para o público: {publico_alvo}.
                    
                    Regras rigorosas:
                    1. Cada pergunta deve ter 4 opções (A, B, C, D).
                    2. Apenas uma opção pode estar correta.
                    3. Para cada pergunta, crie um 'feedback' (que será o flashcard de ensino ativo) explicando a resposta de forma didática.
                    4. Retorne APENAS um código JSON válido neste formato exato (não use blocos de marcação como ```json):
                    [
                        {{
                            "question": "Qual é a capital do Brasil?",
                            "options": ["A) Rio de Janeiro", "B) São Paulo", "C) Brasília", "D) Salvador"],
                            "answer": 2,
                            "feedback": "A capital do Brasil é Brasília, inaugurada em 1960 pelo presidente Juscelino Kubitschek."
                        }}
                    ]
                    
                    Texto base para criar as perguntas:
                    {st.session_state.texto_extraido[:10000]}
                    """
                    
                    resposta = model.generate_content(prompt)
                    
                    # Limpeza do texto caso o Gemini coloque formatação de markdown
                    texto_limpo = resposta.text.replace("```json", "").replace("```", "").strip()
                    
                    # Transforma a resposta de texto num objeto que o Python entende (JSON)
                    dados_quiz = json.loads(texto_limpo)
                    
                    # Guarda o jogo na memória da aplicação
                    st.session_state.dados_quiz = dados_quiz
                    st.success("🎉 Jogo criado com sucesso!")
                    
                except Exception as e:
                    st.error(f"❌ Ocorreu um erro ao comunicar com a Inteligência Artificial: {e}")

# 5. Visualização do Jogo Gerado
if "dados_quiz" in st.session_state:
    st.markdown("---")
    st.subheader("🎮 O Seu Jogo Está Pronto")
    
    for i, pergunta in enumerate(st.session_state.dados_quiz):
        with st.expander(f"Pergunta {i+1}: {pergunta['question']}"):
            for idx_opcao, opcao in enumerate(pergunta['options']):
                if idx_opcao == pergunta['answer']:
                    st.markdown(f"**✅ {opcao}** (Correta)")
                else:
                    st.write(f"❌ {opcao}")
            st.info(f"💡 **Flashcard de Ensino:** {pergunta['feedback']}")
