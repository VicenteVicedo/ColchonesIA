from fastapi import FastAPI, HTTPException, Security, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import mysql.connector
from openai import OpenAI
import json
import os
import pandas as pd
import joblib
import requests
import xml.etree.ElementTree as ET
import traceback
import re
from dotenv import load_dotenv
from parser_markdown import parsear_html_a_markdown
from rag.src.colchones_rag import get_context_embeddings
from rag.src.generar_embeddings import obtener_embeddings
import tools as tool

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
app = FastAPI(title="Chatbot IA - Router System")

# ==========================================
# 1. CARGA DE DATOS (SISTEMA)
# ==========================================

datos_sistema = {
    "modelo": None,
    "catalogo_csv": None,
    "feed_xml": {} 
}

def cargar_datos_al_inicio():
    print("⏳ Iniciando carga de sistema...")
    
    # A. Cargar CSV y Modelo (Solo para colchones)
    try:
        if os.path.exists("encuestas_limpio.csv") and os.path.exists("modelo_satisfaccion.pkl"):
            df = pd.read_csv("encuestas_limpio.csv")
            datos_sistema["catalogo_csv"] = df.drop_duplicates(subset=["cod_articulo"]).copy()
            datos_sistema["modelo"] = joblib.load("modelo_satisfaccion.pkl")
            print("✅ Modelo IA y CSV cargados.")
    except Exception as e:
        print(f"❌ Error cargando CSV/PKL: {e}")

    # B. Cargar XML (Para todo)
    try:
        print(f"⏳ Descargando XML de: {XML_URL} ...")
        response = requests.get(XML_URL, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {'g': 'http://base.google.com/ns/1.0'}
            count = 0
            for item in root.findall('./channel/item'):
                try:
                    g_id_full = item.find('g:id', ns).text.strip()
                    datos_sistema["feed_xml"][g_id_full] = {
                        "id": g_id_full,
                        "titulo": item.find('title').text,
                        "descripcion": item.find('description').text or "",
                        "precio": item.find('g:price', ns).text,
                        "link": item.find('link').text,
                        "imagen": item.find('g:image_link', ns).text
                    }
                    count += 1
                except: continue
            print(f"✅ XML Cargado: {count} productos indexados.")
    except Exception as e:
        print(f"❌ Error procesando XML: {e}")

cargar_datos_al_inicio()


# ==========================================
# 2. DEFINICIÓN DE TOOLS (SEPARADAS)
# ==========================================





# ==========================================
# 3. LÓGICA PYTHON (Generadores de HTML)
# ==========================================

def generar_html_tarjeta(item, razon):
    # 1. LIMPIEZA DE URL (Sanitización)
    # Quitamos espacios, saltos de línea (\n) y posibles etiquetas <br> que se hayan colado
    link_limpio = item['link'].strip().replace('\n', '').replace('\r', '').replace('<br>', '').replace(' ', '')
    titulo_limpio = item['titulo'].strip().replace('\n', '').replace('\r', '').replace('<br>', '').replace(' ', '')
    
    # 2. GENERACIÓN HTML
    return f"""
    <p class="razon">
        <a href="{link_limpio}" target="_blank">{titulo_limpio} ({item['id']})</a> ({razon})
    </p>
    """

def logica_recomendar_colchon(args):
    """CEREBRO MATEMÁTICO (Solo Colchones)"""
    df = datos_sistema["catalogo_csv"]
    modelo = datos_sistema["modelo"]
    feed = datos_sistema["feed_xml"]

    if df is None: return "Error técnico: Modelo no cargado."

    try:
        # Preparación de datos (Igual que antes)
        fila_base = df.iloc[0].copy()
        fila_base["sexo"] = args.get('sexo', 'mujer')
        fila_base["altura"] = float(args.get('altura', 170))
        fila_base["peso"] = float(args.get('peso', 70))
        altura_m = fila_base["altura"] / 100
        fila_base["imc"] = fila_base["peso"] / (altura_m ** 2)
        fila_base["duerme_en_pareja"] = 1 if args.get('duerme_en_pareja', False) else 0
        fila_base["molestias_antes"] = 1 if args.get('molestias_antes', False) else 0

        # Filtro Material
        X_pred = df.copy()
        material = args.get('material_preferido', '').lower()
        if material:
            if "latex" in material or "látex" in material:
                X_pred = X_pred[X_pred['nucleo'].str.contains("latex|látex", case=False, na=False)]
            elif "muelle" in material:
                X_pred = X_pred[X_pred['nucleo'].str.contains("muelle", case=False, na=False)]
            elif "visco" in material:
                X_pred = X_pred[X_pred['nucleo'].str.contains("visco", case=False, na=False)]
            if X_pred.empty: return f"No tenemos colchones de {material} en el catálogo de recomendaciones."

        # Predicción
        cols = ["sexo", "altura", "peso", "imc", "duerme_en_pareja", "molestias_antes"]
        for col in cols: X_pred[col] = fila_base[col]
        features = cols + ["nucleo", "grosor", "firmeza"]
        X_pred["score"] = modelo.predict(X_pred[features])
        candidatos = X_pred.sort_values("score", ascending=False)

        # Matching XML Estricto
        html_output = "He analizado tu perfil y estos son los mejores colchones para ti:<br><br>"
        encontrados = 0
        ids_usados = set()
        claves_xml = list(feed.keys())

        for _, row in candidatos.iterrows():
            if encontrados >= 3: break
            id_csv = str(int(row['cod_articulo']))
            match_key = None
            
            if id_csv in feed: match_key = id_csv
            else:
                patron = r"(^|-)" + re.escape(id_csv) + r"(-|$)"
                for xml_key in claves_xml:
                    if re.search(patron, xml_key):
                        match_key = xml_key
                        break
            
            if match_key and match_key not in ids_usados:
                item = feed[match_key]
                afinidad = round((row["score"]/5)*100)
                html_output += generar_html_tarjeta(item, f"Afinidad: {afinidad}%.)")
                encontrados += 1
                ids_usados.add(match_key)

        if encontrados == 0:
            return "Lo siento, he encontrado modelos ideales para ti, pero **no tenemos stock online** de esas referencias exactas ahora mismo."

        return html_output

    except Exception as e:
        traceback.print_exc()
        return "Error calculando colchón."

def logica_buscar_accesorios(args):
    """CEREBRO BUSCADOR (Keywords en XML)"""
    feed = datos_sistema["feed_xml"]
    keywords = args.get('keywords', '').lower().split()
    resultados = []
    
    # Búsqueda estricta (AND)
    for item in feed.values():
        texto = (item['titulo'] + " " + item['descripcion']).lower()
        if all(kw in texto for kw in keywords):
            resultados.append(item)
    
    # Búsqueda laxa (OR) si no hay resultados
    if not resultados:
        for item in feed.values():
            texto = (item['titulo'] + " " + item['descripcion']).lower()
            if any(kw in texto for kw in keywords):
                resultados.append(item)

    if not resultados:
        return "He buscado en el catálogo y **no he encontrado productos** con esa descripción exacta."

    html_output = f"Aquí tienes lo que he encontrado para '{' '.join(keywords)}':<br><br>"
    for item in resultados[:3]:
        html_output += generar_html_tarjeta(item, "")
        
    return html_output

def logica_consultar_producto_actual(html_input):
    """
    CEREBRO LECTOR (Parser de Ficha)
    Recibe HTML -> Limpia -> Markdown -> OpenAI
    """
    html_a_procesar = ""

    # A. Usar input del usuario
    if html_input and len(html_input) > 100:
        print("✅ Tool: Usando HTML del cliente.")
        html_a_procesar = html_input
    # B. Fallback URL test
    else:
        print(f"⚠️ Tool: Sin HTML. Usando URL fallback.")
        try:
            headers = {'User-Agent': 'Mozilla/5.0 ...'}
            resp = requests.get(URL_FALLBACK_TEST, headers=headers, timeout=10)
            if resp.status_code == 200:
                html_a_procesar = resp.text
            else:
                return "Error: No se pudo cargar la URL de prueba."
        except Exception:
            return "Error: Fallo de conexión."

    # Parsear a Markdown
    info_limpia = parsear_html_a_markdown(html_a_procesar)
    return f"--- FICHA TÉCNICA LEÍDA ---\n\n{info_limpia}"

# ==========================================
# 4. ROUTER (CLASIFICADOR)
# ==========================================

def enrutador_intenciones(mensaje, tiene_html):
    prompt = f"""
    Eres un clasificador de intenciones para el e-commerce Colchones.es.
    Tu trabajo es filtrar lo que entra al chat.
    1. 'RECOMENDADOR': El usuario busca que le recomendemos un colchón (peso, altura, molestiasdolores, etc).
    2. 'BUSCADOR': Busca almohadas, canapés, somieres, bases tapizdas, ropa de cama o una marca específica.
    3. 'FICHA_PRODUCTO': Pregunta detalles del producto que ve en pantalla {'(Tiene ficha abierta)' if tiene_html else '(NO tiene ficha)'}.
    4. 'GENERAL': Saludos, envíos, devoluciones, garantías.
   
    CATEGORÍA DE BLOQUEO:
    5. 'OFF_TOPIC': El usuario pregunta sobre política, deportes, religión, cocina, matemáticas, programación, famosos, clima o CUALQUIER TEMA que no sea descanso o relacionado con un ecommerce de colchones.es.

    Mensaje: "{mensaje}"
    Responde SOLO con la categoría (ej: OFF_TOPIC):"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o", 
            messages=[{"role": "system", "content": prompt}],
            temperature=0, max_tokens=15
        )
        cat = resp.choices[0].message.content.strip()
        print(f"🚦 ROUTER: {cat}")
        return cat
    except:
        return "GENERAL"

# ==========================================
# 5. ENDPOINT Y BD
# ==========================================

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)

def recuperar_historial(user_id, dominio):
    conn = None
    historial = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT pregunta, respuesta FROM my_colchoneses_preguntas_chati WHERE cod_usuario = %s AND dominio = %s AND visible = 1 ORDER BY id DESC LIMIT 10"
        cursor.execute(query, (user_id, dominio))
        rows = cursor.fetchall()
        for row in rows:
            if row['respuesta']:
                historial.append({"role": "assistant", "content": row['respuesta']})
                historial.append({"role": "user", "content": row['pregunta']})
    except Exception as e:
        print(f"Error BD: {e}")
    finally:
        if conn and conn.is_connected(): conn.close()
    return list(reversed(historial))

def guardar_interaccion(datos):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "INSERT INTO my_colchoneses_preguntas_chati (cod_usuario, pregunta, respuesta, url, dominio, articulo, nombre_producto, fecha, visible) VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), 1)"
        art_id = int(datos['articulo_id']) if datos['articulo_id'] else None
        vals = (datos['user_id'], datos['pregunta'], datos['respuesta'], datos['url'], datos['dominio'], art_id, datos['nombre_producto'])
        cursor.execute(query, vals)
        conn.commit()
    except: pass
    finally:
        if conn and conn.is_connected(): conn.close()

class GetContextInput(BaseModel):
    message: str

@app.post("/get_context_rag")
async def get_context_rag_endpoint(input_data: GetContextInput, api_key: str = Security(api_key_header)):
    if api_key != MI_CLAVE_SECRETA:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    contexto_rag = get_context_embeddings(input_data.message)
    return {"context": contexto_rag}

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
    html_contenido: Optional[str] = None # HTML enviado por frontend

@app.post("/chat")
async def chat_endpoint(input_data: ChatInput, api_key: str = Security(api_key_header)):
    if api_key != MI_CLAVE_SECRETA:
        raise HTTPException(status_code=403, detail="Acceso denegado")

    # 1. ENRUTAMIENTO
    tiene_html = bool(input_data.html_contenido and len(input_data.html_contenido) > 50)
    intencion = enrutador_intenciones(input_data.message, tiene_html)
    
    # --- NUEVO: BLOQUEO DE TEMAS ---
    if intencion == "OFF_TOPIC":
        respuesta_off = "Soy un asistente virtual especializado exclusivamente en descanso y productos de Colchones.es. No puedo opinar sobre otros temas, pero estaré encantado de ayudarte a elegir tu próximo equipo de descanso."
        
        # Guardamos la interacción para que conste, pero no gastamos tokens de GPT-4
        guardar_interaccion({
            'user_id': input_data.user_id, 'pregunta': input_data.message, 'respuesta': respuesta_off,
            'url': input_data.url, 'dominio': input_data.dominio, 'articulo_id': input_data.articulo_id, 'nombre_producto': input_data.nombre_producto
        })
        return {"response": respuesta_off}
    # --------------------------------

    # Definimos el SYSTEM PROMPT con una "Personalidad Restrictiva"
    sys_prompt = """Eres el asistente experto de Colchones.es. 
    TU ÚNICO PROPÓSITO es ayudar a los usuarios a dormir mejor y encontrar productos de descanso en la web de colchones.es.
    
    REGLAS DE COMPORTAMIENTO:
    1. Si el usuario saluda, sé amable y profesional.
    2. Si preguntan por política, fútbol, religión o cultura general, RECHAZA amablemente responder diciendo que solo sabes de descanso.
    3. No te inventes opiniones personales."""

    if intencion == "RECOMENDADOR":
        tools_activas = [tool.recomendar]
        sys_prompt += "Tu objetivo es recomendar el colchón ideal. Pide peso y altura si faltan. Usa 'recomendar_colchon'."
    elif intencion == "BUSCAR":
        tools_activas = [tool.buscar_accesorios]
        sys_prompt += "Ayuda a encontrar accesorios o marcas. Usa 'buscar_accesorios_xml'."
    elif intencion == "FICHA_PRODUCTO":
        tools_activas = [tool.consultar_ficha]
        sys_prompt += "Responde dudas sobre el producto que el usuario ve. Usa 'consultar_producto_actual' para leer sus datos."
    else:
        tools_activas = [tool.rag_datos_generales_tienda]
        sys_prompt += "Responde dudas corporativas (envíos, garantías) usando la información de la tienda. Si no está en tu conocimiento, di que no lo sabes."

    sys_prompt += "\nINSTRUCCIÓN FINAL DE RENDERIZADO:"
    sys_prompt += "\nSi una herramienta te devuelve código HTML (etiquetas <a>, <div>, <img>), TU ÚNICA TAREA ES COPIAR Y PEGAR ESE CÓDIGO HTML TAL CUAL EN TU RESPUESTA."
    sys_prompt += "\nNO lo conviertas a Markdown."
    sys_prompt += "\nNO cambies el formato."
    sys_prompt += "\nNO extraigas el texto."
    sys_prompt += "\nSimplemente escupe el HTML crudo que recibas."

    # 2. CHAT CON OPENAI
    historial = recuperar_historial(input_data.user_id, input_data.dominio)
    messages = [{"role": "system", "content": sys_prompt}] + historial + [{"role": "user", "content": input_data.message}]

    try:
        kwargs = {
            "model": "gpt-4o",
            "messages": messages,
            "temperature": 0.3,       # <--- CAMBIO CRÍTICO: Cero creatividad
            "top_p": 0.2,           # <--- EXTRA: Solo considera el top 10% de probabilidad
            "frequency_penalty": 0, # No penalizar repetición de términos técnicos
            "presence_penalty": 0
        }
        if tools_activas:
            kwargs["tools"] = tools_activas
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        msg_ia = response.choices[0].message
        
        respuesta_final = ""

        if msg_ia.tool_calls:
            tool_call = msg_ia.tool_calls[0]
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            res_tool = ""

            if name == "recomendar_colchon":
                res_tool = logica_recomendar_colchon(args)
            elif name == "buscar_accesorios_xml":
                res_tool = logica_buscar_accesorios(args)
            elif name == "consultar_producto_actual":
                res_tool = logica_consultar_producto_actual(input_data.html_contenido)
            elif name == "buscar_info_general":
                res_tool = get_context_embeddings(input_data.message)
            
            messages.append(msg_ia)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": res_tool})
            
            final = client.chat.completions.create(model="gpt-4o", messages=messages)
            respuesta_final = final.choices[0].message.content
        else:
            respuesta_final = msg_ia.content

        guardar_interaccion({
            'user_id': input_data.user_id, 'pregunta': input_data.message, 'respuesta': respuesta_final,
            'url': input_data.url, 'dominio': input_data.dominio, 'articulo_id': input_data.articulo_id, 'nombre_producto': input_data.nombre_producto
        })
        return {"response": respuesta_final}

    except Exception as e:
        traceback.print_exc()
        return {"response": "Lo siento, hubo un error técnico en el servidor."}