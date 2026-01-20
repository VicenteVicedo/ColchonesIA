from fastapi import FastAPI, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import Optional, Any
import mysql.connector
from openai import OpenAI
import json
import os
import pandas as pd
import joblib
import requests
import xml.etree.ElementTree as ET
import traceback
from datetime import datetime
from dotenv import load_dotenv
from parser_markdown import parsear_html_a_markdown
from rag.src.colchones_rag import get_context_embeddings
from rag.src.generar_embeddings import obtener_embeddings

# =====================================================
# CONFIGURACIÓN GENERAL
# =====================================================
load_dotenv()

API_KEY_NAME = "x-api-key"
MI_CLAVE_SECRETA = os.getenv("MI_CLAVE_SECRETA")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
XML_URL = "https://www.colchones.es/gmerchantcenter_dofinder.xml"
LOG_FILE = "agent_decisions.log"

# URL para cuando probamos el bot fuera de la web (Postman, consola, etc.)
URL_FALLBACK_TEST = "https://www.colchones.es/colchones/juvenil-First-Sac-muelles-ensacados-viscoelastica-fibras/"

DB_CONFIG = {
    'user': 'chati',
    'password': os.getenv("DB_PASSWORD_CHATI"),
    'host': 'localhost',
    'database': 'colchones',
    'raise_on_warnings': True
}

client = OpenAI(api_key=OPENAI_API_KEY)
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
app = FastAPI(title="Chatbot IA - Backend Multiagente")

# =====================================================
# LOGGER DE AGENTES
# =====================================================

def log_agente(user_id, pregunta, agente, argumentos, resultado):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "user_id": user_id,
                "pregunta": pregunta,
                "agente": agente,
                "argumentos": argumentos,
                "resultado_preview": str(resultado)[:300]
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass

# =====================================================
# 1. CARGA DE DATOS
# =====================================================

datos_sistema = {
    "modelo": None,
    "catalogo_csv": None,
    "feed_xml": {}
}

def cargar_datos_al_inicio():
    df = pd.read_csv("encuestas_limpio.csv")
    datos_sistema["catalogo_csv"] = df.drop_duplicates(subset=["cod_articulo"]).copy()
    datos_sistema["modelo"] = joblib.load("modelo_satisfaccion.pkl")

    response = requests.get(XML_URL, timeout=10)
    root = ET.fromstring(response.content)
    ns = {'g': 'http://base.google.com/ns/1.0'}

    for item in root.findall('./channel/item'):
        try:
            g_id = item.find('g:id', ns).text.split('-')[0]
            if g_id not in datos_sistema["feed_xml"]:
                datos_sistema["feed_xml"][g_id] = {
                    "titulo": item.find('title').text,
                    "precio": item.find('g:price', ns).text,
                    "link": item.find('link').text,
                    "imagen": item.find('g:image_link', ns).text
                }
        except:
            continue

cargar_datos_al_inicio()

# =====================================================
# 2. TOOLS (AGENTES)
# =====================================================

tools_openai = [
    {
        "type": "function",
        "function": {
            "name": "recomendar_colchon",
            "description": "Recomienda colchones y solo colchones según perfil físico",
            "parameters": {
                "type": "object",
                "properties": {
                    "sexo": {"type": "string", "enum": ["hombre", "mujer"]},
                    "altura": {"type": "number"},
                    "peso": {"type": "number"},
                    "duerme_en_pareja": {"type": "boolean"},
                    "tiene_dolor_espalda": {"type": "boolean"},
                    "molestias_antes": {"type": "boolean"},
                    "material_preferido": {"type": "string"}
                },
                "required": ["sexo", "altura", "peso"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_info_general",
            "description": "Información general sobre descanso",
            "parameters": {
                "type": "object",
                "properties": {"pregunta": {"type": "string"}},
                "required": ["pregunta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_producto_actual",
            "description": "EJECUTAR CUANDO: El usuario haga preguntas sobre el producto que está viendo en pantalla (firmeza, precio, materiales, etc). DEVUELVE: La información técnica leída directamente de la ficha del producto.",
            "parameters": {
                "type": "object",
                "properties": {}, # No requiere parámetros, usa el contexto actual
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_catalogo",
            "description": "Busca productos en catálogo XML",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    }
]

# =====================================================
# 3. AGENTES (HANDLERS)
# =====================================================

def buscar_info_general(pregunta):
    return f"Según nuestros expertos, la respuesta a '{pregunta}' depende de la firmeza, postura al dormir y transpirabilidad del colchón."

def consultar_producto_actual(html_input):
    """
    1. Recibe el HTML crudo (o None).
    2. Si es None, descarga la URL de prueba.
    3. Lo pasa por el parser_markdown para limpiarlo.
    4. Devuelve el texto estructurado a OpenAI.
    """
    html_a_procesar = ""

    # CASO A: El frontend nos envió el HTML (Usuario real navegando)
    if html_input and len(html_input) > 100:
        print("✅ Tool: Usando HTML recibido del cliente.")
        html_a_procesar = html_input
        
    # CASO B: No hay HTML (Estamos probando en local/Postman) -> Usamos URL Default
    else:
        print(f"⚠️ Tool: No hay HTML de entrada. Descargando URL de test...")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0'}
            resp = requests.get(URL_FALLBACK_TEST, headers=headers, timeout=10)
            if resp.status_code == 200:
                html_a_procesar = resp.text
            else:
                return "Error sistema: No se pudo descargar la ficha de producto de prueba."
        except Exception as e:
            return f"Error sistema: Fallo de conexión ({str(e)})."

    # CASO C: Procesado (Aquí ocurre la magia de limpieza)
    # Convertimos el HTML sucio en Markdown limpio (#, |, -)
    info_limpia = parsear_html_a_markdown(html_a_procesar)
    
    # Añadimos una cabecera para que OpenAI sepa qué es esto
    return f"--- INFORMACIÓN LEÍDA DE LA FICHA DEL PRODUCTO ---\n\n{info_limpia}"


def buscar_en_catalogo(query):
    resultados = []
    for info in datos_sistema["feed_xml"].values():
        if query.lower() in info["titulo"].lower():
            resultados.append(f"{info['titulo']} ({info['precio']})")
        if len(resultados) >= 5:
            break
    return "\n".join(resultados) if resultados else "No se encontraron productos."

def recomendar_colchon(args):
    df = datos_sistema["catalogo_csv"]
    modelo = datos_sistema["modelo"]
    feed = datos_sistema["feed_xml"]

    args.setdefault("duerme_en_pareja", False)
    args.setdefault("tiene_dolor_espalda", False)
    args.setdefault("molestias_antes", False)

    X = df.copy()

    material = args.get("material_preferido")
    if material:
        X = X[X["nucleo"].str.contains(material, case=False, na=False)]
        if X.empty:
            return json.dumps([])

    altura_m = args["altura"] / 100
    imc = args["peso"] / (altura_m ** 2)

    X["sexo"] = args["sexo"]
    X["altura"] = args["altura"]
    X["peso"] = args["peso"]
    X["imc"] = imc
    X["duerme_en_pareja"] = int(args["duerme_en_pareja"])
    X["molestias_antes"] = int(args["molestias_antes"])

    features = ["sexo","altura","peso","imc","duerme_en_pareja","molestias_antes","nucleo","grosor","firmeza"]
    X["score"] = modelo.predict(X[features])

    X = X.sort_values("score", ascending=False)

    recomendaciones = []
    for _, r in X.iterrows():
        cod = str(int(r["cod_articulo"]))
        if cod in feed:
            afinidad = round((r["score"] / 5) * 100)
            if afinidad < 70:
                continue
            recomendaciones.append({
                "nombre": feed[cod]["titulo"],
                "afinidad": f"{afinidad}%",
                "precio": feed[cod]["precio"],
                "imagen": feed[cod]["imagen"],
                "link": feed[cod]["link"]
            })
        if len(recomendaciones) == 3:
            break

    return json.dumps(recomendaciones)

# =====================================================
# 4. BD: HISTORIAL
# =====================================================

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def recuperar_historial(user_id, dominio):
    conn = None
    historial = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT pregunta, respuesta
            FROM my_colchoneses_preguntas_chati
            WHERE cod_usuario = %s AND dominio = %s AND visible = 1
            ORDER BY id DESC
            LIMIT 10
        """
        cursor.execute(query, (user_id, dominio))
        rows = cursor.fetchall()
        for row in rows:
            if row["respuesta"]:
                historial.append({"role": "assistant", "content": row["respuesta"]})
                historial.append({"role": "user", "content": row["pregunta"]})
    except Exception as e:
        print("Error historial:", e)
    finally:
        if conn and conn.is_connected():
            conn.close()
    return list(reversed(historial))

def guardar_interaccion(datos):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = """
            INSERT INTO my_colchoneses_preguntas_chati
            (cod_usuario, pregunta, respuesta, url, dominio, articulo, nombre_producto, fecha, visible)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), 1)
        """
        art_id = int(datos["articulo_id"]) if datos["articulo_id"] else None
        cursor.execute(query, (
            datos["user_id"], datos["pregunta"], datos["respuesta"],
            datos["url"], datos["dominio"], art_id, datos["nombre_producto"]
        ))
        conn.commit()
    except Exception as e:
        print("Error guardar:", e)
    finally:
        if conn and conn.is_connected():
            conn.close()

# =====================================================
# 5. ENDPOINT CHAT (ORQUESTADOR)
# =====================================================
class EmbeddingGenerationInput(BaseModel):
    url: Optional[str]

@app.post('/generar_embeddings')
async def generar_embedding_paginas(
    req: Optional[EmbeddingGenerationInput] = None, # Permitimos que req sea None
    api_key: str = Security(api_key_header)
):
    if api_key != MI_CLAVE_SECRETA:
        raise HTTPException(status_code=403, detail="Acceso denegado")
   
    # Extraemos la url si req existe, si no, pasamos None
    url_a_procesar = req.url if req else None
    
    obtener_embeddings(urls=url_a_procesar)
    
    return {
        "status": "success", 
        "message": f"Procesando: {url_a_procesar if url_a_procesar else 'Lista completa'}"
    }

class ChatInput(BaseModel):
    user_id: str
    message: str
    url: Optional[str] = ""
    dominio: Optional[str] = "colchones.es"
    articulo_id: Optional[Any] = None
    nombre_producto: Optional[str] = None

@app.post("/chat")
async def chat_endpoint(input_data: ChatInput, api_key: str = Security(api_key_header)):
    if api_key != MI_CLAVE_SECRETA:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    system_prompt = """Eres el asistente experto de Colchones.es.
Decide qué herramienta usar según la intención del usuario.
Usa las herramientas disponibles cuando sea necesario y no inventes datos."""

    historial = recuperar_historial(input_data.user_id, input_data.dominio)

    contexto_rag = get_context_embeddings(input_data.message)

    messages = (
        [{"role": "system", "content": system_prompt}]
        + historial 
        + [{
            "role": "user", 
            "content": f"Contexto:\n{contexto_rag}\n\nPregunta: {input_data.message}"
        }]
        #+ [{"role": "user", "content": input_data.message}]
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools_openai,
            tool_choice="auto"
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            tool = msg.tool_calls[0]
            args = json.loads(tool.function.arguments)

            if tool.function.name == "recomendar_colchon":
                res = recomendar_colchon(args)
            elif tool.function.name == "buscar_info_general":
                res = buscar_info_general(args["pregunta"])
            elif tool.function.name == "consultar_producto_actual":
                res = consultar_producto_actual(input_data.html_contenido)
            elif tool.function.name == "buscar_en_catalogo":
                res = buscar_en_catalogo(args["query"])
            else:
                res = "No se pudo procesar la solicitud."

            log_agente(input_data.user_id, input_data.message, tool.function.name, args, res)

            messages.append(msg)
            messages.append({"role": "tool", "tool_call_id": tool.id, "content": res})

            final = client.chat.completions.create(model="gpt-4o", messages=messages)
            respuesta_final = final.choices[0].message.content
        else:
            respuesta_final = msg.content

        guardar_interaccion({
            "user_id": input_data.user_id,
            "pregunta": input_data.message,
            "respuesta": respuesta_final,
            "url": input_data.url,
            "dominio": input_data.dominio,
            "articulo_id": input_data.articulo_id,
            "nombre_producto": input_data.nombre_producto
        })

        return {"response": respuesta_final}

    except Exception:
        traceback.print_exc()
        return {"response": "<br>Lo siento, no puedo responder a esa pregunta, reformúlala o puedes dejarnos un correo o teléfono para que nos pongamos en contacto contigo:<div class=\"bloqueLeadChati\"><input type=\"text\" placeholder=\"Correo o teléfono\" style=\"width:85%; padding:8px;\" name=\"telefonoCorreoCliente\" id=\"telefonoCorreoCliente\"/>            <input type=\"hidden\" name=\"cookieUsuario\" id=\"cookieUsuario\" value=\"'.$_COOKIE[\"nuevoVisitante2\"].'\"/><input type=\"hidden\" name=\"articuloVisitado\" id=\"articuloVisitado\" value=\"'.$articulo.'\"/>            <button type=\"button\" style=\"padding: 10px 9px;    cursor: pointer;    background: #4c9b9d;    float: right;    border: solid 1px #4c9b9d;\" onclick=\"enviarContactoChati()\" id=\"telefonoCorreoCliente2\">             <img src=\"https://cdn-icons-png.flaticon.com/512/60/60525.png\" alt=\"Enviar\" style=\"width:16px; height:16px; vertical-align:middle;filter: brightness(0) invert(1);\"></button>       </div>"}
