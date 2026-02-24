from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import List

router = APIRouter()

# Lista global de conexões WebSocket ativas
active_connections: List[WebSocket] = []

@router.websocket("/ws/orders")
async def websocket_orders(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Mantém a conexão aberta, não precisa receber nada
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

# Função utilitária para notificar todos os clientes conectados
async def notify_orders_update():
    for ws in list(active_connections):
        try:
            await ws.send_text("update")
        except Exception:
            try:
                active_connections.remove(ws)
            except Exception:
                pass
