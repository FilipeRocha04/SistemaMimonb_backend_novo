import asyncio
import json
import logging
import os
from typing import Awaitable, Callable, Dict, Optional

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger("app.redis_bus")

_CHANNEL = "mimonb:broadcast"

_publish_client: Optional["redis.Redis"] = None
_listener_task: Optional[asyncio.Task] = None


def _redis_url() -> Optional[str]:
    return os.getenv("REDIS_URL")


def is_enabled() -> bool:
    return redis is not None and bool(_redis_url())


async def try_publish(kind: str, payload: dict) -> bool:
    """Publica um evento no canal compartilhado do Redis.

    Retorna True se o evento foi publicado (nesse caso os workers, inclusive
    o atual, vão receber e processar via listener). Retorna False se o Redis
    não está configurado/disponível, para que o chamador faça o fallback
    local (broadcast direto neste processo, como antes do Redis existir).
    """
    global _publish_client
    if not is_enabled():
        return False
    try:
        if _publish_client is None:
            _publish_client = redis.from_url(_redis_url(), decode_responses=True)
        await _publish_client.publish(_CHANNEL, json.dumps({"kind": kind, "payload": payload}))
        return True
    except Exception:
        logger.exception("Falha ao publicar evento no Redis; seguindo com fallback local")
        return False


def start_listener(handlers: Dict[str, Callable[[dict], Awaitable[None]]]) -> None:
    """Inicia (em background) a escuta do canal compartilhado do Redis.

    Cada worker do gunicorn chama isso no startup. Quando qualquer worker
    publica um evento, TODOS os workers (inclusive o publicador) recebem
    aqui e disparam o handler local correspondente, garantindo que clientes
    WebSocket/SSE conectados em qualquer processo sejam notificados.
    """
    global _listener_task
    if not is_enabled():
        logger.warning(
            "REDIS_URL não configurado: notificações não terão fan-out entre "
            "múltiplos workers (cada processo só avisa seus próprios clientes)."
        )
        return

    async def _listen():
        while True:
            try:
                client = redis.from_url(_redis_url(), decode_responses=True)
                pubsub = client.pubsub()
                await pubsub.subscribe(_CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        data = json.loads(message["data"])
                    except Exception:
                        continue
                    handler = handlers.get(data.get("kind"))
                    if handler is None:
                        continue
                    try:
                        await handler(data.get("payload") or {})
                    except Exception:
                        logger.exception("Erro ao processar evento '%s' vindo do Redis", data.get("kind"))
            except Exception:
                logger.exception("Conexão com o listener do Redis caiu; tentando de novo em 3s")
                await asyncio.sleep(3)

    _listener_task = asyncio.create_task(_listen())
