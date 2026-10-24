st.set_page_config(page_title="Quizify", layout="centered")

def obter_segredo(chave):
    import os
    # 1. Tenta ler do Render primeiro
    valor = os.environ.get(chave)
    if valor:
        return valor
    
    # 2. Se estiver no seu computador, usa o Streamlit
    if os.path.exists(".streamlit/secrets.toml"):
        return st.secrets[chave]
        
    # 3. Se não encontrar, mostra exatamente qual chave está a falhar!
    raise ValueError(f"FALTA CONFIGURAR NO RENDER: A variável '{chave}' não foi encontrada ou o nome está errado.")

try:
    # 1. Configurar Gemini
    GEMINI_API_KEY = obter_segredo("GEMINI_API_KEY")
    genai.configure(api_key=GEMINI_API_KEY)
    modelo = genai.GenerativeModel("gemini-3.8-flash")
    
    # 2. Configurar Firebase
    if not firebase_admin._apps:
        chave_json = obter_segredo("FIREBASE_KEY")
        cert_dict = json.loads(chave_json)
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred, {
            'storageBucket': obter_segredo("FIREBASE_BUCKET")
        })
except Exception as e:
    st.error(f"Erro de configuração: {e}")
    st.stop()
