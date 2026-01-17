"""
RESTful server wrapper around the existing RAG `answer_question` function.

Provides a single POST /ask endpoint that accepts JSON:
  {"user_id": "...", "pregunta": "...", "history_items": 10}

and returns:
  {"respuesta": "..."}

This file uses FastAPI + Uvicorn. To run:

  pip install fastapi uvicorn
  uvicorn src.ia_server_restful:app --host 0.0.0.0 --port 8000

If your environment doesn't have FastAPI, install it in your virtualenv.
"""

from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import asyncio

from pregunta import answer_question

app = FastAPI(title="ColchonesIA - IA REST API")


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


# Small health endpoint
@app.get("/health")
def health():
    return {"status": "ok"}
