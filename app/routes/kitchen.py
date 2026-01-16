from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.responses import StreamingResponse
import json
import asyncio

from app.utils.pubsub import register_queue, unregister_queue, register_ws, unregister_ws, get_status, publish

router = APIRouter(prefix="/kitchen", tags=["Kitchen"])
from app.utils.pubsub import get_status


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
    # Use StreamingResponse with text/event-stream so we don't rely on EventSourceResponse availability
    return StreamingResponse(event_generator(request), media_type="text/event-stream")


@router.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
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
def status():
    # simple debug endpoint
    try:
        return get_status()
    except Exception:
        return {"error": "failed to get status"}


@router.post('/test-publish')
async def test_publish(payload: dict):
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
