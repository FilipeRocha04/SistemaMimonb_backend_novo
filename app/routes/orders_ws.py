import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List, Optional

from app.utils import redis_bus
from app.services.auth import decode_token

router = APIRouter()

# Lista global de conexões WebSocket ativas
active_connections: List[WebSocket] = []

# Loop principal (asyncio) do processo, capturado no startup do FastAPI.
# Necessário porque as rotas de pedidos são funções sync e rodam numa
# threadpool (sem event loop próprio), então não podem usar
# asyncio.create_task diretamente para notificar os clientes WebSocket.
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


def schedule_coroutine(coro) -> None:
    """Agenda uma coroutine no loop principal, de forma thread-safe.

    Funciona tanto quando chamado de dentro do event loop (rotas async)
    quanto de uma thread da threadpool (rotas sync), que é o caso comum
    das rotas de pedidos hoje.
    """
    if _main_loop is None:
        coro.close()
        return
    try:
        asyncio.run_coroutine_threadsafe(coro, _main_loop)
    except Exception:
        coro.close()

@router.websocket("/ws/pedidos")
async def websocket_orders(websocket: WebSocket):
    # Autenticação do WebSocket: o navegador não permite enviar o header
    # "Authorization" no handshake de WS, então o token vem via query string
    # (?token=...), validado (assinatura + expiração) antes do accept().
    # Sem token válido, a conexão é recusada antes de entrar na lista de
    # broadcast — assim ninguém não autenticado recebe os sinais de
    # atualização de pedidos/cozinha.
    token = websocket.query_params.get("token")
    payload = decode_token(token) if token else None
    if not payload or not payload.get("sub"):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Mantém a conexão aberta, não precisa receber nada
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

# Notifica apenas os clientes WebSocket conectados a ESTE processo/worker.
async def broadcast_local(_payload: dict | None = None) -> None:
    for ws in list(active_connections):
        try:
            await ws.send_text("update")
        except Exception:
            try:
                active_connections.remove(ws)
            except Exception:
                pass


# Função pública chamada pelas rotas de pedidos. Publica no Redis para que
# TODOS os workers do gunicorn avisem seus próprios clientes; se o Redis não
# estiver configurado (ex: dev local), cai para o broadcast local de sempre.
async def notify_orders_update():
    published = await redis_bus.try_publish("orders_update", {})
    if not published:
        await broadcast_local()
