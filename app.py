import streamlit as st
import PyPDF2
import time

# Configuração da página
st.set_page_config(page_title="Quizify - Aprenda a Jogar", page_icon="🧩", layout="centered")

st.title("🧩 Quizify")
st.markdown("### Transforme qualquer material num jogo interativo")
st.write("Crie quizzes e flashcards a partir de PDFs para os seus alunos, filhos ou para o seu próprio estudo.")

# 1. Memória da aplicação (para não perder os dados e os botões não sumirem)
if "material_processado" not in st.session_state:
    st.session_state.material_processado = False
if "texto_extraido" not in st.session_state:
    st.session_state.texto_extraido = ""

# 2. Área de Upload
st.markdown("---")
st.subheader("1. Envie o material base")
arquivo_pdf = st.file_uploader("Faça o upload do documento em PDF (Apostila, Resumo, Matéria)", type=["pdf"])

# 3. Lógica de processamento do PDF
if arquivo_pdf is not None:
    if st.button("Analisar Documento", type="primary"):
        with st.spinner("A extrair informações do documento..."):
            try:
                # Leitura do PDF
                leitor_pdf = PyPDF2.PdfReader(arquivo_pdf)
                texto = ""
                
                for pagina in leitor_pdf.pages:
                    texto_pagina = pagina.extract_text()
                    if texto_pagina:
                        texto += texto_pagina + "\n"
                
                if not texto.strip():
                    st.error("⚠️ O PDF parece estar vazio ou é uma imagem digitalizada sem texto reconhecível.")
                else:
                    st.session_state.texto_extraido = texto
                    st.session_state.material_processado = True
                    time.sleep(1) # Simula o processamento
                    st.success("✅ Documento analisado com sucesso!")
                    
            except Exception as e:
                st.error(f"❌ Erro ao ler o arquivo: {e}")

# 4. Área de Geração do Jogo (Só aparece depois do PDF ser lido com sucesso)
if st.session_state.material_processado:
    st.markdown("---")
    st.subheader("2. Configure o seu Jogo")
    
    # Opções para personalizar o Quiz
   # Opções para personalizar o Quiz (Agora com ENEM e Concursos)
    publico_alvo = st.selectbox(
        "Para quem é este jogo?", 
        [
            "Alunos (Ensino Fundamental)", 
            "Alunos (Ensino Médio)", 
            "Estudantes para o ENEM",
            "Candidatos a Concursos Públicos",
            "Filhos (Estudo em Casa)", 
            "Treinamento Corporativo / Geral"
        ]
    )    
    if st.button("✨ Gerar Quizz e Flashcards"):
        st.info(f"Em breve: A Inteligência Artificial vai pegar no texto lido e criar um jogo de {quantidade_perguntas} perguntas focado no público: {publico_alvo}.")
        
        # Aqui, no futuro, colocaremos o código que envia o st.session_state.texto_extraido 
        # para a API (como a da OpenAI/ChatGPT ou Claude) devolver o código HTML do joguinho.
