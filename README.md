# 🎲 Quizify

Transforma PDF, Word, PowerPoint e fotos (até 5 de cada vez) em quizzes e flashcards interativos com o Google Gemini.
O resultado é um HTML autônomo publicado no Firebase (link para Android, iOS e computador) e que também pode ser baixado para uso offline.

## Estrutura

```
app.py                  # Flask: rotas, extração de texto, Gemini, Firebase (só Python)
templates/index.html    # página principal (Tailwind)
templates/quiz.html     # quiz gerado — autônomo, sem CDN, funciona offline
templates/flashcards.html
static/js/main.js       # upload, compressão de imagens no navegador, download do HTML
```

## Variáveis de ambiente (Render → Environment)

| Variável | Descrição |
|---|---|
| `GEMINI_API_KEY` | Chave da API do Google Gemini |
| `GEMINI_MODEL` | (opcional) modelo; padrão `gemini-3.8-flash` |
| `FIREBASE_KEY` | JSON da conta de serviço do Firebase (conteúdo inteiro, numa linha) |
| `FIREBASE_BUCKET` | Nome do bucket, ex.: `meu-projeto.appspot.com` |

## Render

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --workers 2 --timeout 180`
- **Cron-job:** aponte para `https://SEU-DOMINIO/health` (resposta leve, não chama a IA).

## Rodar localmente

```bash
pip install -r requirements.txt
flask --app app run --debug
```
