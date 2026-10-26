"""Configuração do gunicorn, lida automaticamente ao rodar `gunicorn app:app`.

Cada geração passa a maior parte do tempo esperando a IA (rede), por isso usamos
threads: enquanto uma requisição espera o Gemini, as outras são atendidas.
Ajustável no Render pelas variáveis WEB_CONCURRENCY e GUNICORN_THREADS.
"""
import os

worker_class = "gthread"
workers = int(os.environ.get("WEB_CONCURRENCY", 2))          # processos
threads = int(os.environ.get("GUNICORN_THREADS", 8))         # requisições simultâneas por processo
timeout = 180                                                # a IA pode demorar com muitos arquivos
graceful_timeout = 30
keepalive = 5
# Recicla cada processo de tempos em tempos para a memória não crescer sem parar.
max_requests = 1000
max_requests_jitter = 100
