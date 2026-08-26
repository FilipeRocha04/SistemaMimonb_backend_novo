from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse
import json
import asyncio

from app.utils.pubsub import register_queue, unregister_queue, register_ws, unregister_ws, get_status, publish
from app.services.auth import decode_token, get_current_user

# NOTA: este router não está incluído em app.main atualmente (código morto/
# órfão — o frontend usa /ws/orders, de orders_ws.py, para tudo em tempo
# real da cozinha). Protegido mesmo assim (deny-by-default) para o caso de
# ser registrado futuramente.
router = APIRouter(prefix="/cozinha", tags=["Kitchen"])
from app.utils.pubsub import get_status


def _require_token_from_query(request_or_ws) -> dict:
    """Valida o token JWT vindo via query string (?token=...).

    Usado por /stream (SSE) e /ws (WebSocket), onde o cliente não consegue
    enviar o header Authorization no handshake.
    """
    token = request_or_ws.query_params.get("token")
    payload = decode_token(token) if token else None
    if not payload or not payload.get("sub"):
        return None
    return payload


async def event_generator(request: Request):
    q = register_queue()
    try:
        while True:
            # if client disconnected, stop
            if await request.is_disconnected():
                break
            try:
                event = await q.get()
            except asyncio.CancelledError:
                break
            # yield as server-sent event
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        unregister_queue(q)


@router.get("/stream")
def stream(request: Request):
    # EventSource do navegador não envia header Authorization; token vem via
    # query string (?token=...).
    if not _require_token_from_query(request):
        raise HTTPException(status_code=401, detail="Token inválido ou ausente")
    # Use StreamingResponse with text/event-stream so we don't rely on EventSourceResponse availability
    return StreamingResponse(event_generator(request), media_type="text/event-stream")


@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    if not _require_token_from_query(websocket):
        await websocket.close(code=1008)
        return
    # accept connection and register websocket
    await websocket.accept()
    register_ws(websocket)
    try:
        # keep the connection open; if client sends data we simply ignore it
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                # ignore receive errors and loop to keep connection alive
                await asyncio.sleep(0.1)
    finally:
        try:
            unregister_ws(websocket)
        except Exception:
            pass


@router.get('/status')
def status(current_user=Depends(get_current_user)):
    # simple debug endpoint
    try:
        return get_status()
    except Exception:
        return {"error": "failed to get status"}


@router.post('/test-publish')
async def test_publish(payload: dict, current_user=Depends(get_current_user)):
    """Development helper: publish an arbitrary event to connected clients."""
    try:
        # schedule publish without blocking
        try:
            asyncio.create_task(publish(payload))
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.create_task(publish(payload))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}
