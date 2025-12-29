import asyncio
import json
import logging
from typing import Any

import websockets

from pregunta import answer_question, history_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def handle_connection(ws: websockets.WebSocketServerProtocol):
    logger.info("Client connected: %s", ws.remote_address)
    try:
        async for message in ws:
            try:
                data = json.loads(message)
            except Exception:
                await ws.send(json.dumps({"error": "Invalid JSON"}, ensure_ascii=False))
                continue

            if not isinstance(data, dict):
                await ws.send(json.dumps({"error": "Expected JSON object"}, ensure_ascii=False))
                continue

            # Support two actions: send a question, or retrieve history
            #action = data.get("action") or "ask"
#
            #if action == "ask":
            user_id = data.get("user_id", "default")
            pregunta = data.get("pregunta")
            if not pregunta or not isinstance(pregunta, str):
                await ws.send(json.dumps({"error": "No 'pregunta' field provided"}, ensure_ascii=False))
                continue

            # Call the potentially blocking answer_question in a thread
            loop = asyncio.get_running_loop()
            try:
                # answer_question signature: (pregunta, user_id, history_items)
                respuesta = await loop.run_in_executor(None, lambda: answer_question(pregunta, user_id))
            except Exception as e:
                logger.exception("Error answering question")
                await ws.send(json.dumps({"error": str(e)}, ensure_ascii=False))
                continue

            payload: Any = {"respuesta": respuesta}
            await ws.send(json.dumps(payload, ensure_ascii=False))

            #elif action == "get_history":
            #    user_id = data.get("user_id")
            #    if not user_id or not isinstance(user_id, str):
            #        await ws.send(json.dumps({"error": "No 'user_id' field provided"}, ensure_ascii=False))
            #        continue
            #    n = data.get("n", 50)
            #    try:
            #        user_history = history_manager.get(user_id)
            #        messages = [dict(role=m.role, content=m.content) for m in user_history.last_messages(n)]
            #        await ws.send(json.dumps({"history": messages}, ensure_ascii=False))
            #    except Exception as e:
            #        logger.exception("Error retrieving history")
            #        await ws.send(json.dumps({"error": str(e)}, ensure_ascii=False))
            #        continue

            #else:
            #    await ws.send(json.dumps({"error": f"Unknown action: {action}"}, ensure_ascii=False))
            #    continue

    except websockets.ConnectionClosed:
        logger.info("Client disconnected: %s", ws.remote_address)


async def main(host: str = "127.0.0.1", port: int = 8765):
    logger.info("Starting WebSocket server on %s:%d", host, port)
    
    # Usamos el context manager de websockets.serve para mayor limpieza
    async with websockets.serve(handle_connection, host, port):
        # Esto mantiene el servidor corriendo indefinidamente
        await asyncio.Future()  # Mantiene el loop ocupado

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
