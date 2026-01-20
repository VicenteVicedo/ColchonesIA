"""
RESTful server wrapper around the existing RAG `answer_question` function.
Configured with CORS to allow requests from any origin.
"""

from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # Importación necesaria
from pydantic import BaseModel
import asyncio

from pregunta import answer_question

app = FastAPI(title="ColchonesIA - IA REST API")

# --- Configuración de CORS ---
# Esto permite que tu navegador acepte la respuesta del servidor 
# cuando la petición viene de un dominio o puerto distinto.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite cualquier origen. Cambiar a ["http://localhost:5500"] en producción.
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos (POST, GET, etc.)
    allow_headers=["*"],  # Permite todas las cabeceras
)

class AskRequest(BaseModel):
    pregunta: str
    user_id: Optional[str] = "default"
    history_items: Optional[int] = 10


class AskResponse(BaseModel):
    respuesta: str


@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    if not req.pregunta:
        raise HTTPException(status_code=400, detail="'pregunta' is required")
    try:
        # answer_question is blocking; run in thread
        respuesta = await asyncio.to_thread(answer_question, req.pregunta, req.user_id, req.history_items)
        return AskResponse(respuesta=respuesta)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health():
    return {"status": "ok"}