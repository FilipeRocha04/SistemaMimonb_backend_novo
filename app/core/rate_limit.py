"""Rate limiting compartilhado (slowapi).

Instância única de Limiter, importável tanto por app.main (para registrar o
middleware/exception handler) quanto pelas rotas que precisam de limites mais
restritivos que o padrão global (ex.: login).

LIMITAÇÃO CONHECIDA: o slowapi, por padrão, guarda os contadores em memória
do próprio processo. Isso é adequado para o cenário atual (um restaurante,
processo único), mas se a aplicação passar a rodar com múltiplos workers/
processos (ex.: gunicorn -w N) ou múltiplas instâncias atrás de um load
balancer, cada processo terá sua própria contagem independente — o limite
efetivo vira (limite configurado x número de processos), e não é
compartilhado entre eles. Se isso deixar de ser aceitável, a solução correta
é um backend de armazenamento compartilhado (ex.: Redis, já usado no projeto
para o pub/sub de pedidos) via `storage_uri` do slowapi, e não uma
reimplementação caseira.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Limite global por IP, aplicado a toda rota que não tiver um limite próprio
# mais restritivo. Generoso o suficiente para não atrapalhar o uso normal do
# app (polling/websocket de cozinha, telas de pedidos), mas bloqueia abuso.
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
