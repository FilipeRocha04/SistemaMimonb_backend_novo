import asyncio
from typing import List, Any
from starlette.websockets import WebSocket

# In-memory pub/sub: support both EventSource (asyncio.Queue) and WebSocket clients
_subscribers: List[asyncio.Queue] = []
_websockets: List[WebSocket] = []


def register_queue() -> asyncio.Queue:
    q = asyncio.Queue()
    _subscribers.append(q)
    return q


def unregister_queue(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass


def register_ws(ws: WebSocket) -> None:
    try:
        _websockets.append(ws)
    except Exception:
        pass


def unregister_ws(ws: WebSocket) -> None:
    try:
        _websockets.remove(ws)
    except ValueError:
        pass


async def publish(event: Any) -> None:
    # small debug print to help trace events in dev
    try:
        print(f"[pubsub] publish event: {event.get('type') if isinstance(event, dict) else str(type(event))}")
    except Exception:
        pass

    # put the event into all subscriber queues (SSE)
    for q in list(_subscribers):
        try:
            await q.put(event)
        except Exception:
            # best-effort; ignore failures
            pass

    # broadcast to connected WebSocket clients (best-effort)
    for ws in list(_websockets):
        try:
            # send_json is an async coroutine on Starlette WebSocket
            await ws.send_json(event)
        except Exception:
            try:
                _websockets.remove(ws)
            except Exception:
                pass


def get_status() -> dict:
    """Return a small debug status for dev: number of SSE queues and WS clients."""
    return {"sse_queues": len(_subscribers), "websockets": len(_websockets)}
