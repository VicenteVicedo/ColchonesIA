from openai import OpenAI
import requests
import json
import os

# =========================
# CONFIGURACIÓN
# =========================

# NOTA: Usa gpt-4o o gpt-3.5-turbo. "gpt-4.1" no existe.
MODELO_OPENAI = "gpt-4o" 

# TU CLAVE DE OPENAI (Bórrala de aquí si compartes el código)
client = OpenAI(api_key="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")

# TU CLAVE DE FASTAPI (La que definiste en main.py)
API_KEY_FASTAPI = "colchones_secretos_2026_pro_v1" 
API_URL = "http://127.0.0.1:8000/recomendar"

# =========================
# FUNCIÓN PARA CONSULTAR LA API
# =========================

def consultar_modelo(datos):
    # 1. AÑADIMOS LAS CABECERAS DE SEGURIDAD
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_KEY_FASTAPI # <--- ¡ESTO FALTABA!
    }
    
    try:
        r = requests.post(API_URL, json=datos, headers=headers, timeout=10)
        r.raise_for_status() # Esto lanzará error si da 403 o 500
        return r.json()
    except requests.exceptions.HTTPError as err:
        return {"error": f"Error conectando con FastAPI: {err}"}
    except Exception as e:
        return {"error": f"Error desconocido: {e}"}

# =========================
# MEMORIA DE CONVERSACIÓN
# =========================

messages = [
    {
        "role": "system",
        "content": (
            "Eres un asistente experto en descanso y recomendación de colchones. "
            "Tu objetivo es RECOMENDAR un colchón, no pedir confirmaciones. "
            "Haz solo las preguntas estrictamente necesarias para obtener estos datos del usuario: "
            "sexo, peso, altura, si duerme en pareja, si tiene dolor de espalda y si tiene molestias antes de dormir. "
            "Cuando tengas TODOS esos datos, DEBES llamar inmediatamente a la función recomendar_colchon. "
            "NO preguntes si quiere más detalles. "
            "NO pidas confirmación. "
            "NO sigas conversando sin llamar a la función. "
            "Tras recibir la respuesta de la función, explica la recomendación de forma clara y directa."
        )
    }
]

# =========================
# DEFINICIÓN DE TOOLS
# =========================

tools = [{
    "type": "function",
    "function": {
        "name": "recomendar_colchon",
        "description": "Recomienda el mejor colchón según el perfil del usuario",
        "parameters": {
            "type": "object",
            "properties": {
                "sexo": {"type": "string", "enum": ["hombre", "mujer"]},
                "altura": {"type": "number", "description": "en cm"},
                "peso": {"type": "number", "description": "en kg"},
                "duerme_en_pareja": {"type": "boolean"},
                "tiene_dolor_espalda": {"type": "boolean"},
                "molestias_antes": {"type": "boolean"}
            },
            "required": ["sexo", "altura", "peso"]
        }
    }
}]

# =========================
# BUCLE PRINCIPAL
# =========================

print("--- INICIANDO CHAT DE PRUEBA (Escribe 'salir' para terminar) ---")

while True:
    user_input = input("Tú: ")
    if user_input.lower() in ["salir", "exit"]:
        break

    messages.append({"role": "user", "content": user_input})

    # Llamada a OpenAI
    response = client.chat.completions.create(
        model=MODELO_OPENAI, # Usamos el modelo correcto
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    msg = response.choices[0].message

    # =========================
    # LÓGICA DE HERRAMIENTAS
    # =========================

    if msg.tool_calls:
        print("🛠️  (El sistema ha detectado todos los datos. Consultando IA Local...)")
        
        args = json.loads(msg.tool_calls[0].function.arguments)

        # ✅ VALORES POR DEFECTO
        args.setdefault("duerme_en_pareja", False)
        args.setdefault("tiene_dolor_espalda", False)
        args.setdefault("molestias_antes", False)

        # LLAMADA A TU API FASTAPI LOCAL
        resultado = consultar_modelo(args)

        # Guardar mensaje del assistant (tool call)
        messages.append(msg)

        # Guardar respuesta de la tool (lo que devolvió FastAPI)
        messages.append({
            "role": "tool",
            "tool_call_id": msg.tool_calls[0].id,
            "content": json.dumps(resultado)
        })

        # OpenAI genera la respuesta final leyendo el JSON de FastAPI
        final = client.chat.completions.create(
            model=MODELO_OPENAI,
            messages=messages
        )

        print(f"🤖 Chatbot: {final.choices[0].message.content}")
        
        # Opcional: Romper bucle tras recomendar o seguir charlando
        # break 

    else:
        # Si no tiene datos suficientes, sigue preguntando
        print(f"🤖 Chatbot: {msg.content}")
        messages.append(msg)