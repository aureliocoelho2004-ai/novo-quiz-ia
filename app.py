import streamlit as st
import google.generativeai as genai
import streamlit.components.v1 as components
from PIL import Image

# Configuração inicial da página
st.set_page_config(page_title="Gerador de Quiz", layout="centered")

# Configurar a API do Gemini utilizando o secrets do Streamlit
try:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
except KeyError:
    st.error("Chave de API não configurada. Verifique os Secrets no painel do Streamlit Cloud.")
    st.stop()

st.title("📚 Gerador de Quiz Educacional")
st.write("Envie uma foto do material de estudo para gerar um jogo interativo.")

# Área para o utilizador enviar a foto do livro
uploaded_file = st.file_uploader("Tire uma foto ou anexe a imagem (JPG, JPEG, PNG)", type=["jpg", "jpeg", "png"])

if uploaded_file is not None:
    # Carregar e exibir a imagem na interface
    image = Image.open(uploaded_file)
    st.image(image, caption="Material recebido para análise", use_container_width=True)

    # Botão para iniciar a geração
    if st.button("Gerar Jogo"):
        with st.spinner("A analisar o conteúdo e a construir o quiz..."):
            try:
                # Inicializar o modelo multimodal rápido do Gemini
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # Instrução rigorosa para gerar o código do jogo com a nova regra de fonte
                prompt = """
                Atue como um professor criativo. Leia o conteúdo educacional desta imagem e crie um jogo de quiz interativo de múltipla escolha baseado nos conceitos presentes nela.
                O retorno deve ser EXCLUSIVAMENTE o código HTML completo e funcional de uma única página (Single Page Application).
                O código deve conter:
                1. CSS embutido: Design moderno, amigável para crianças/estudantes e responsivo. DESTAQUE VISUAL: A dica ou instrução que pede ao utilizador para "clicar na resposta correta" deve ter uma fonte bem grande e chamativa (ex: font-size: 24px ou maior, em negrito).
                2. JavaScript embutido: Lógica para validar respostas, avançar para a próxima pergunta e exibir a pontuação final de forma lúdica.
                Não inclua formatações markdown (como ```html), devolva estritamente o código limpo.
                """
                
                # Enviar a imagem e o comando para a IA
                response = model.generate_content([prompt, image])
                
                # Limpar formatações residuais do modelo, se existirem
                html_gerado = response.text.replace("```html", "").replace("```", "").strip()
                
                st.success("Quiz gerado com sucesso!")
                
                # Renderizar o HTML diretamente na página (solução compatível com iOS/Safari)
                components.html(html_gerado, height=750, scrolling=True)
                
            except Exception as e:
                st.error(f"Ocorreu um erro durante a geração: {e}")
