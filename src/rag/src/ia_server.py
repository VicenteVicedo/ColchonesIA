import asyncio
import json
import logging
import os
from typing import Any
import websockets
from websockets.server import ServerConnection
import ssl

from colchones_rag import configuration
from pregunta import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# El formato del mensaje entrante es JSON:
# {
#     "user_id": "usuario123",
#     "pregunta": "¿Cuál es la mejor manera de dormir bien?"
#     "context": {
#       "key1": "value1",
#       "key2": "value2",
#           ...
#     }
# }

async def handle_connection(ws: ServerConnection):
    logger.info("Client connected: %s", ws.remote_address)
    try:
        async for message in ws:
            try:
                data = json.loads(message)
            except Exception:
                await ws.send(json.dumps({"error": "Invalid JSON"}, ensure_ascii=False))
                continue

            #Si pregunta no está en el JSON o no es str, error
            if not isinstance(data, dict):
                await ws.send(json.dumps({"error": "Expected JSON object"}, ensure_ascii=False))
                continue

            user_id = data.get("user_id", "default")
            pregunta = data.get("pregunta")
            if not pregunta or not isinstance(pregunta, str):
                await ws.send(json.dumps({"error": "No 'pregunta' field provided"}, ensure_ascii=False))
                continue

            try:
                respuesta = await asyncio.to_thread(answer_question, pregunta, user_id)
            except Exception as e:
                logger.exception("Error answering question")
                await ws.send(json.dumps({"error": str(e)}, ensure_ascii=False))
                continue

            payload: Any = {"respuesta": respuesta}
            await ws.send(json.dumps(payload, ensure_ascii=False))

    except websockets.ConnectionClosed:
        logger.info("Client disconnected: %s", ws.remote_address)

async def main(host: str = "127.0.0.1", port: int = 8765):
    logger.info("Starting WebSocket server on %s:%d", host, port)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    
    # Rutas a tus archivos de certificado
    cert_file = "ssl/certificado.pem"
    key_file = "ssl/clave_privada.key"

    try:
        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        logger.info("SSL certificates loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load SSL certificates: {e}")
        return
    
    # El servidor reconoce automáticamente que el manejador tiene un solo argumento (ws)
    async with websockets.serve(handle_connection, host, port, ssl=ssl_context):
        # Mantiene el servidor corriendo indefinidamente de forma limpia
        await asyncio.get_running_loop().create_future() 

if __name__ == "__main__":
    try:
        # Crear las carpetas necesarias para los historiales si no existen
        histories_path = configuration.get("histories_dir", "histories")
        os.makedirs(histories_path, exist_ok=True)

        # Lanzar el servidor WebSocket
        asyncio.run(main('0.0.0.0', 8765))
    except KeyboardInterrupt:
        logger.info("Server stopped by user")