import streamlit as st
import PyPDF2
import time
from PIL import Image
import pytesseract

# Configuração da página
st.set_page_config(page_title="Quizify - Aprenda a Jogar", page_icon="🧩", layout="centered")

st.title("🧩 Quizify")
st.markdown("### Transforme qualquer material num jogo interativo")
st.write("Crie quizzes e flashcards a partir de PDFs ou Imagens para os seus alunos, filhos ou para o seu próprio estudo.")

# 1. Memória da aplicação
if "material_processado" not in st.session_state:
    st.session_state.material_processado = False
if "texto_extraido" not in st.session_state:
    st.session_state.texto_extraido = ""

# 2. Área de Upload (Agora aceita Imagens também)
st.markdown("---")
st.subheader("1. Envie o material base")
arquivo = st.file_uploader("Faça o upload do documento (PDF, PNG, JPG, JPEG)", type=["pdf", "png", "jpg", "jpeg"])

# 3. Lógica de processamento do PDF ou Imagem
if arquivo is not None:
    if st.button("Analisar Documento", type="primary"):
        with st.spinner("A extrair informações do documento..."):
            try:
                texto = ""
                
                # Se for um PDF
                if arquivo.name.lower().endswith('.pdf'):
                    leitor_pdf = PyPDF2.PdfReader(arquivo)
                    for pagina in leitor_pdf.pages:
                        texto_pagina = pagina.extract_text()
                        if texto_pagina:
                            texto += texto_pagina + "\n"
                            
                # Se for uma Imagem
                elif arquivo.name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    imagem = Image.open(arquivo)
                    # O pytesseract vai tentar ler o texto da imagem (em português, se o pacote estiver instalado)
                    try:
                        texto = pytesseract.image_to_string(imagem, lang='por')
                    except Exception:
                        # Se não tiver o pacote de português, tenta o padrão
                        texto = pytesseract.image_to_string(imagem)
                
                if not texto.strip():
                    st.error("⚠️ Não foi possível encontrar texto neste arquivo. Se for uma imagem, certifique-se de que está nítida.")
                else:
                    st.session_state.texto_extraido = texto
                    st.session_state.material_processado = True
                    time.sleep(1) # Simula o processamento
                    st.success("✅ Texto extraído com sucesso!")
                    
            except Exception as e:
                st.error(f"❌ Erro ao processar o arquivo: {e}\n\nSe for um erro de Tesseract não encontrado, é necessário instalar as dependências do sistema.")

# 4. Área de Geração do Jogo
if st.session_state.material_processado:
    st.markdown("---")
    st.subheader("2. Configure o seu Jogo")
    
    # Pré-visualização do texto lido
    with st.expander("Ver texto extraído do documento"):
        st.write(st.session_state.texto_extraido[:1000] + ("..." if len(st.session_state.texto_extraido) > 1000 else ""))
    
    # Opções para personalizar o Quiz
    publico_alvo = st.selectbox(
        "Para quem é este jogo?", 
        [
            "Alunos (Ensino Fundamental)", 
            "Alunos (Ensino Médio)", 
            "Alunos (Ensino Superior)",
            "Estudantes para o ENEM",
            "Candidatos a Concursos Públicos",
            "Filhos (Estudo em Casa)", 
            "Treinamento Corporativo / Geral"
        ]
    )
    
    quantidade_perguntas = st.slider("Quantas perguntas deseja gerar?", min_value=5, max_value=50, value=10)
    
    if st.button("✨ Gerar Quizz e Flashcards"):
        st.info(f"Em breve: A Inteligência Artificial vai processar o texto extraído e criar um jogo de {quantidade_perguntas} perguntas focado no público: {publico_alvo}.")
