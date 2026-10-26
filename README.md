# 🎲 Quizify

Transforma PDF, Word, PowerPoint e fotos (até 5 de cada vez) em quizzes e flashcards interativos com o Google Gemini.
O resultado é um HTML autônomo publicado no Firebase (link para Android, iOS e computador) e que também pode ser baixado para uso offline.

## Estrutura

```
app.py                  # Flask: rotas, extração de texto, Gemini, Firebase (só Python)
templates/base.html     # layout comum (Tailwind)
templates/index.html    # página principal
templates/login.html, trocar_senha.html, admin.html
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
| `SECRET_KEY` | Texto longo e aleatório para assinar as sessões de login (ex.: `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `LIMITE_DIARIO` | (opcional) conteúdos por utilizador por dia; padrão 50 (admins não têm limite) |
| `LIMITE_TESTE` | (opcional) conteúdos por dia em contas de teste; padrão 10 |
| `INFINITEPAY_HANDLE` | Sua InfiniteTag (sem o `$`). Sem ela, os pagamentos ficam desligados |
| `URL_PUBLICA` | Endereço do site, ex.: `https://app.quizzify.com.br` (usado nos links de retorno e aviso) |
| `PRECO_MENSAL_CENTAVOS` / `PRECO_ANUAL_CENTAVOS` | (opcional) preços em centavos; padrão 2990 e 29900 |
| `INFINITEPAY_WEBHOOK_TOKEN` | (opcional) segredo do endereço de aviso; por padrão é derivado da `SECRET_KEY` |
| `INFINITEPAY_API_KEY` | (opcional) chave da API, se a InfinitePay exigir |
| `INTERVALO_SEGUNDOS` | (opcional) espera mínima entre gerações; padrão 30 |
| `ADMIN_USER` / `ADMIN_PASSWORD` | (opcional) cria o primeiro admin quando ainda não existe `usuarios.json` no Firebase |

## Login

- Utilizadores ficam em `usuarios.json` no Firebase, com senhas em hash (nunca em texto puro).
- Contas do formato antigo (Streamlit) continuam a funcionar e são obrigadas a trocar a senha no primeiro acesso.
- O admin gere utilizadores em `/admin` (criar, redefinir senha, remover). Senhas definidas pelo admin são provisórias.
- Contas de teste (24 h, 3 dias ou 7 dias) são criadas em `/admin`, entram direto com a senha definida, nunca são admin e expiram sozinhas; o admin pode prolongar +24 h.
- Após 5 tentativas erradas, o login fica bloqueado por 10 minutos para aquele IP.

## Render

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn app:app --workers 2 --timeout 180`
- **Cron-job:** aponte para `https://SEU-DOMINIO/health` (resposta leve, não chama a IA).

## Rodar localmente

```bash
pip install -r requirements.txt
flask --app app run --debug
```

## Assinaturas (InfinitePay)

1. A pessoa cria a conta em `/cadastro` (e-mail e senha) e é levada a `/assinatura`.
2. Escolhe mensal (30 dias) ou anual (365 dias); o app cria um pedido em `pedidos/<id>.json` e abre o Checkout Integrado.
3. Após o pagamento, a InfinitePay chama `/webhooks/infinitepay` e devolve o cliente a `/assinatura/retorno`.
   Nos dois casos o app confirma o pagamento na própria InfinitePay (`payment_check`) antes de liberar.
4. Os dias somam-se ao que já existe; sem renovação, o acesso fica bloqueado até novo pagamento.
5. No `/admin`, cada assinante mostra a validade e há o botão "Liberar +30 dias" para casos de suporte.
   Se um pagamento for confirmado mas não creditado, o log do Render mostra `PAGAMENTO SEM CRÉDITO`.
