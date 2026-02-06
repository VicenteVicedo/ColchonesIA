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
import unicodedata
from dotenv import load_dotenv
from parser_markdown import parsear_html_a_markdown
from rag.src.colchones_rag import get_context_embeddings
from rag.src.generar_embeddings import obtener_embeddings
import tools as tool

load_dotenv()

API_KEY_NAME = "x-api-key"
MI_CLAVE_SECRETA = os.getenv("MI_CLAVE_SECRETA")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
XML_URL = "https://www.colchones.es/gmerchantcenter_chati.xml"
LOG_FILE = "agent_decisions.log"

# URL para cuando probamos el bot fuera de la web (Postman, consola, etc.)
URL_FALLBACK_TEST = "https://www.colchones.es/colchones/juvenil-First-Sac-muelles-ensacados-viscoelastica-fibras/"

DB_CONFIG = {
    'user': os.getenv("DB_user"),
    'password': os.getenv("DB_PASSWORD_CHATI"),
    'host': os.getenv("DB_host"),
    'database': os.getenv("DB_database"),
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
        <a href="{link_limpio}" target="_blank">{titulo_limpio}</a> ({razon})
    </p>
    """
# ==========================================
# 3. LÓGICA PYTHON (Generadores de HTML)
# ==========================================

def generar_html_tarjeta_buscador(item):
    # 1. LIMPIEZA DE URL (Sanitización)
    print(f"Producto encontrado: {item['titulo']}")
    # Quitamos espacios, saltos de línea (\n) y posibles etiquetas <br> que se hayan colado
    link_limpio = item['link'].strip().replace('\n', '').replace('\r', '').replace('<br>', '').replace(' ', '')
    titulo_limpio = item['titulo'].strip().replace('\n', '').replace('\r', '').replace('<br>', '').replace(' ', '')
    descripcion = item['descripcion'].strip().replace('\n', '').replace('\r', '').replace('<br>', '').replace(' ', '')
    
    # 2. GENERACIÓN HTML
    return f"""
    <p class="razon">
        <a href="{link_limpio}" target="_blank">{titulo_limpio}</a> {descripcion}
    </p>
    """

def logica_recomendar_colchon(args, user_id):
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
            return f"Lo siento, <b>no he encontrado modelos</b> ideales para ti, puedes dejarnos un correo o teléfono para poder contactar contigo: <div class='bloqueLeadChati'><input type='text' placeholder='Correo o teléfono' style='width:85%; padding:8px;' name='telefonoCorreoCliente' id='telefonoCorreoCliente'/><input type='hidden' name='cookieUsuario' id='cookieUsuario' value='{user_id}'/><input type='hidden' name='articuloVisitado' id='articuloVisitado' value=''/><button type='button' style='padding: 10px 9px;    cursor: pointer;    background: #4c9b9d;    float: right;    border: solid 1px #4c9b9d;' onclick='enviarContactoChati()' id='botonEnviarContactoChati'><img src='https://cdn-icons-png.flaticon.com/512/60/60525.png' alt='Enviar' style='width:16px; height:16px; vertical-align:middle;filter: brightness(0) invert(1);'></button></div>"

        return html_output

    except Exception as e:
        traceback.print_exc()
        return f"Lo siento, <b>no he encontrado modelos</b> ideales para ti, puedes dejarnos un correo o teléfono para poder contactar contigo: <div class='bloqueLeadChati'><input type='text' placeholder='Correo o teléfono' style='width:85%; padding:8px;' name='telefonoCorreoCliente' id='telefonoCorreoCliente'/><input type='hidden' name='cookieUsuario' id='cookieUsuario' value='{user_id}'/><input type='hidden' name='articuloVisitado' id='articuloVisitado' value=''/><button type='button' style='padding: 10px 9px;    cursor: pointer;    background: #4c9b9d;    float: right;    border: solid 1px #4c9b9d;' onclick='enviarContactoChati()' id='botonEnviarContactoChati'><img src='https://cdn-icons-png.flaticon.com/512/60/60525.png' alt='Enviar' style='width:16px; height:16px; vertical-align:middle;filter: brightness(0) invert(1);'></button></div>"

def logica_buscar_accesorios(args, user_id):
    """
    CEREBRO BUSCADOR MEJORADO (Búsqueda por Puntuación/Weighted Search)
    """
    feed = datos_sistema["feed_xml"]
    raw_keywords = args.get('keywords', '').lower().split()

    # 1. DEFINIR STOP WORDS (Palabras a ignorar para reducir ruido)
    stop_words = {'de', 'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o', 'para', 'con', 'en'}
    keywords = [kw for kw in raw_keywords if kw not in stop_words and len(kw) > 2]

    if not keywords:
         # Si después de limpiar no quedan keywords (ej: el usuario solo puso "de la"), usar las originales
         keywords = raw_keywords

    # --- FUNCIÓN AUXILIAR PARA QUITAR ACENTOS ---
    def normalizar_texto(texto):
        if not texto: return ""
        # Esto transforma "Colchón Viscoelástico" en "colchon viscoelastico"
        return ''.join(c for c in unicodedata.normalize('NFD', texto.lower())
                       if unicodedata.category(c) != 'Mn')
    # -------------------------------------------

    resultados_con_puntuacion = []

    # 2. BÚSQUEDA CON PUNTUACIÓN
    for item in feed.values():
        score = 0
        coincidencias_palabras = 0
        
        # Normalizamos textos del XML una vez
        titulo_norm = normalizar_texto(item['titulo'])
        descripcion_norm = normalizar_texto(item.get('descripcion', '')) # Usamos get por si no hay descripción

        for kw in keywords:
            kw_norm = normalizar_texto(kw)
            palabra_encontrada = False

            # REGLA 1: El título vale mucho más (x5 veces más que la descripción)
            if kw_norm in titulo_norm:
                score += 10
                palabra_encontrada = True
            
            # REGLA 2: La descripción vale menos, pero suma
            # Usamos 'elif' para no sumar doble si está en los dos sitios por la misma palabra
            elif kw_norm in descripcion_norm:
                score += 2
                palabra_encontrada = True
            
            if palabra_encontrada:
                coincidencias_palabras += 1

        # REGLA 3: Bonus enorme si encontramos TODAS las palabras buscadas
        # Esto recupera el comportamiento "estricto" pero lo prioriza en lugar de filtrar.
        if coincidencias_palabras == len(keywords) and len(keywords) > 0:
            score += 30

        # Si el producto tiene alguna relevancia, lo guardamos
        if score > 0:
            # Guardamos una tupla: (puntuación, objeto_item)
            resultados_con_puntuacion.append((score, item))

    # 3. ORDENAR RESULTADOS POR PUNTUACIÓN DESCENDENTE (Mayor puntuación primero)
    # x[0] es el score
    resultados_con_puntuacion.sort(key=lambda x: x[0], reverse=True)

    # Extraemos solo los items ya ordenados
    resultados_finales = [item for score, item in resultados_con_puntuacion]

    # 4. GENERACIÓN DE RESPUESTA (Igual que antes)
    if not resultados_finales:
        # Usamos f-string aquí también por si acaso
        return f"He buscado en el catálogo y <b>no he encontrado productos</b> con esa descripción. Puedes dejarnos un correo o teléfono para poder contactar contigo: <div class='bloqueLeadChati'><input type='text' placeholder='Correo o teléfono' style='width:85%; padding:8px;' name='telefonoCorreoCliente' id='telefonoCorreoCliente'/><input type='hidden' name='cookieUsuario' id='cookieUsuario' value='{user_id}'/><input type='hidden' name='articuloVisitado' id='articuloVisitado' value=''/><button type='button' style='padding: 10px 9px; cursor: pointer; background: #4c9b9d; float: right; border: solid 1px #4c9b9d;' onclick='enviarContactoChati()' id='botonEnviarContactoChati'><img src='https://cdn-icons-png.flaticon.com/512/60/60525.png' alt='Enviar' style='width:16px; height:16px; vertical-align:middle;filter: brightness(0) invert(1);'></button></div>"

    html_output = f"Aquí tienes los resultados más relevantes para '{' '.join(raw_keywords)}':<br><br>"
    
    # Mostramos el top 3
    for item in resultados_finales[:3]:
        # Opcional: Puedes mostrar la puntuación para depurar:
        # html_output += generar_html_tarjeta(item, f"Relevancia: Alta") 
        html_output += generar_html_tarjeta_buscador(item)
        
    return html_output

def logica_consultar_producto_actual(html_input, user_id):
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

def enrutador_intenciones(mensaje, tiene_html, esta_en_ficha, historial):
    print(f"Enrutador: {tiene_html}")
    contexto_para_router = formatear_historial_para_router(historial, ultimos_n=3)
    if tiene_html:
        prompt = f"""
        Eres un clasificador de intenciones para el e-commerce Colchones.es.
        Tu trabajo es filtrar lo que entra al chat.
        1. 'RECOMENDADOR': El usuario busca que le recomendemos un colchón (peso, altura, molestias, dolores, etc) interpreta bien si la pregunta es ambigua o se refiere al producto visitado, si crees que hace referencia al producto visitado, usa la herramienta 'FICHA_PRODUCTO' .
        2. 'BUSCADOR': Busca colchones (siempre que no pregunte sobre el colchon de la ficha que esté {esta_en_ficha}), almohadas, canapés, somieres, bases tapizdas, ropa de cama. También puedes consultar esta herramienta para conseguir URLs de producto si el usuario te lo pidiera. USALA solo si la intención es devolver un listado de productos, urls de producto o una caracteristica de algun producto concreto.
        3. 'FICHA_PRODUCTO': El usuario Pregunta detalles del producto que ve en pantalla (caracteristicas, precio de alguna medida, plazos de entrega, opiniones, fabricacion, donde probarlo o donde comprarlo, si es recomendable este producto para el. Si crees que la pregunta en el contexto hace referencia al producto actual que está viendo el cliente es IMPORTANTE QUE PRIORICES esta información: {esta_en_ficha} .
        4. 'GENERAL': Saludos, envíos, devoluciones, garantías y temas relacionados con estas keywords (sobre-como-comprar, sobre-formas-de-pago, sobre-envio-recepcion-pedido, -atencion-cliente, como-dormir-bien, como-elegir-un-colchon-y-base, mejores-colchones-ocu-2025, compromisos de nuestra web, sobre-garantias,rebajas-ofertas-descuentos-promociones,firmeza-del-colchon,medidas-de-colchones,tipos-de-colchones,colchones-estilos-de-vida,consejos-colchon-latex,consejos-colchon-viscoelastica,consejos-limpiar-cambiar-colchon,como-elegir-un-colchon-y-base/composicion-somier-laminas,como-elegir-un-colchon-y-base/estructura-canapes-y-tapas,como-elegir-un-colchon-y-base/sistemas-apertura-canapes,informacion-fibromialgia-o-fatiga-cronica-y-el-colchon-mas-adecuado,)
        5. 'GENERAL_MARCA': si el usuario pregunta por nuestras marcas de manera générica.
       
        CATEGORÍA DE BLOQUEO:
        6. 'OFF_TOPIC': El usuario pregunta sobre política, deportes, religión, cocina, matemáticas, programación, famosos, clima o CUALQUIER TEMA que no sea descanso o relacionado con un ecommerce de colchones.es.
        ---
        CONTEXTO PREVIO (Últimos mensajes):
        {contexto_para_router}
        ---
        MENSAJE ACTUAL DEL USUARIO: "{mensaje}"
        ---
        Responde SOLO con la categoría (ej: OFF_TOPIC):"""       
    else:
        prompt = f"""
        Eres un clasificador de intenciones para el e-commerce Colchones.es.
        Tu trabajo es filtrar lo que entra al chat.
        1. 'RECOMENDADOR': El usuario busca que le recomendemos un colchón (peso, altura, molestias).
        2. 'BUSCADOR': Busca colchones (siempre que no pregunte sobre el colchon de la ficha que esté {esta_en_ficha}), almohadas, canapés, somieres, bases tapizdas, ropa de cama. También puedes consultar esta herramienta para conseguir URLs de producto si el usuario te lo pidiera. USALA solo si la intención es devolver un listado de productos, urls de producto o una caracteristica de algun producto concreto.      
        3. 'GENERAL': Saludos, envíos, devoluciones, garantías y temas relacionados con estas keywords (sobre-como-comprar, sobre-formas-de-pago, sobre-envio-recepcion-pedido, -atencion-cliente, como-dormir-bien, como-elegir-un-colchon-y-base, mejores-colchones-ocu-2025, compromisos de nuestra web, sobre-garantias,rebajas-ofertas-descuentos-promociones,firmeza-del-colchon,medidas-de-colchones,tipos-de-colchones,colchones-estilos-de-vida,consejos-colchon-latex,consejos-colchon-viscoelastica,consejos-limpiar-cambiar-colchon,como-elegir-un-colchon-y-base/composicion-somier-laminas,como-elegir-un-colchon-y-base/estructura-canapes-y-tapas,como-elegir-un-colchon-y-base/sistemas-apertura-canapes,informacion-fibromialgia-o-fatiga-cronica-y-el-colchon-mas-adecuado,)
        4. 'GENERAL_MARCA': si el usuario pregunta por nuestras marcas de manera générica.
        5. 'OFF_TOPIC': El usuario pregunta sobre política, deportes, religión, cocina, matemáticas, programación, famosos, clima o CUALQUIER TEMA que no sea descanso o relacionado con un ecommerce de colchones.es.
        ---
        CONTEXTO PREVIO (Últimos mensajes):
        {contexto_para_router}
        ---
        MENSAJE ACTUAL DEL USUARIO: "{mensaje}"
        ---
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

def formatear_historial_para_router(historial_lista, ultimos_n=2):
    """
    Convierte los últimos N mensajes del historial en un string de texto plano
    para dar contexto rápido al router.
    Ej:
    Asistente: ¿Cuánto mides?
    Usuario: 1,90
    """
    if not historial_lista:
        return "Sin contexto previo."
        
    # Tomamos solo los últimos N mensajes para no saturar al router
    historial_reciente = historial_lista[-ultimos_n:]
    
    texto_contexto = ""
    for msg in historial_reciente:
        role = "Asistente" if msg['role'] == 'assistant' else "Usuario"
        texto_contexto += f"{role}: {msg['content']}\n"
    
    return texto_contexto.strip()

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

    contexto_rag, sources = get_context_embeddings(input_data.message)
    return {"context": contexto_rag, "sources": sources}

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
    esta_en_ficha = input_data.nombre_producto
    historial = recuperar_historial(input_data.user_id, input_data.dominio)
    intencion = enrutador_intenciones(input_data.message, tiene_html, esta_en_ficha, historial)
    
    # --- NUEVO: BLOQUEO DE TEMAS ---
    if intencion == "OFF_TOPIC":
        respuesta_off = f"Soy un asistente virtual especializado exclusivamente en descanso y productos de Colchones.es. No puedo opinar sobre otros temas, reformula tu pregunta o puedes dejarnos un correo o teléfono para poder contactar contigo: <div class='bloqueLeadChati'>        <input type='text' placeholder='Correo o teléfono' style='width:85%; padding:8px;' name='telefonoCorreoCliente' id='telefonoCorreoCliente'/>        <input type='hidden' name='cookieUsuario' id='cookieUsuario' value='{input_data.user_id}'/>     <input type='hidden' name='articuloVisitado' id='articuloVisitado' value='{input_data.articulo_id}'/> <button type='button' style='padding: 10px 9px;    cursor: pointer;    background: #4c9b9d;    float: right;    border: solid 1px #4c9b9d;' onclick='enviarContactoChati()' id='botonEnviarContactoChati'>Enviar</button></div>"
        
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

    RESTRICCIONES DE RESPUESTA
    1. Siempre máximo 100 palabras.
    2. Nunca inventes información.

    ATENCIÓN AL CLIENTE
    * L-V: 8 am - 20 pm
    * Email: info@colchones.es
    * WhatsApp: 657 657 780
    * Teléfono: 900 701 086 (tel. gratuito)
    
    GLOSARIO DE TÉRMINOS
    * “lamas” = láminas
    * “visco” = viscoelástica (aunque aparezca con nombres de marca, equivale a viscoelástica con beneficios similares).
    * “hr” = espumación HR
    * “colores” o “terminaciones” en canapés = acabados (se ven en ficha/desplegable).
    * “grueso” o “grosor” en colchones = altura (ej: 150x200x31 = 31 cm). A más grosor, más confort.
    * “lateral” o “faldón” en ropa de cama = alto (ej: 90x180x27 → válido para colchones de hasta 27 cm).
    * “colchones de muelles” = muelles tradicionales.
    * "bases" = somier de láminas, canapé o base tapizada.
    * “entresacados / embolsados / encastrados” = muelles ensacados.
    * "firmeza" = dureza. Se refiere a una característica del producto.
    * "firme" = duro.
    * "durmientes" = personas
    * "personas sudorosas, que sudan, con sudor" = personas calurosas
    * "saco" = funda nórdica.
    * Diferencia: muelles tradicionales (unidos) vs. muelles ensacados (independientes, mayor adaptabilidad).
    * “tiempo de entrega” = plazo de entrega.
    * "usar solo por una cara" = una cara útil
    * "ficha fábrica" = ficha técnica
    * "aguanta" = soporta

    
    REGLAS DE COMPORTAMIENTO:
    1. Si el usuario saluda, sé amable y profesional.
    2. Si preguntan por política, fútbol, religión o cultura general, RECHAZA amablemente responder diciendo que solo sabes de descanso.
    3. No te inventes opiniones personales."""

    if intencion == "RECOMENDADOR":
        tools_activas = [tool.recomendar]
        sys_prompt += "Tu objetivo es recomendar el colchón ideal. Pide peso y altura si faltan. Usa 'recomendar_colchon'."
    elif intencion == "BUSCADOR":
        tools_activas = [tool.buscar_accesorios]
        sys_prompt += "Ayuda a encontrar productos, urls de productos o marcas. Usa 'buscar_accesorios_xml'."
    elif intencion == "FICHA_PRODUCTO":
        tools_activas = [tool.consultar_ficha]
        sys_prompt += "Responde dudas sobre el producto que el usuario esta viendo en la web (precio, datos del producto, donde probarlo o donde comprarlo) (te pasamos el contenido integro de la ficha de producto). Usa 'consultar_producto_actual' para leer sus datos ."
    elif intencion == "GENERAL_MARCA":
        tools_activas = [tool.rag_datos_generales_tienda]
        sys_prompt += "Responde dudas usando la información de la tienda. Si no está en tu conocimiento, di que no lo sabes."
    else:
        tools_activas = [tool.rag_datos_generales_tienda]
        sys_prompt += "Responde dudas usando la información de la tienda. Si no está en tu conocimiento, di que no lo sabes."
    
    sys_prompt += """    
    INSTRUCCIONES DE FORMATO Y MAQUETACIÓN:
    1. Tu respuesta se mostrará en una web, así que USA HTML para estructurar el texto y poner enlaces (usa <p> para párrafos, por ejemplo). No uses ** ** para resaltar palabras, usa negritas con la etiqueta <strong>
    2. NUNCA devuelvas un "muro de texto" denso. Se claro y CONCISO. Y usa correctamente los signos de puntuación: detrás de un punto y una coma irá un espacio.
    3. Si tienes que listar pasos, requisitos o puntos importantes, usa listas desordenadas HTML:
       <ul>
         <li><strong>Concepto clave:</strong> Explicación...</li>
         <li><strong>Otro punto:</strong> Explicación...</li>
       </ul>
    4. Usa etiquetas <br> para separar párrafos.
    5. Usa <strong> para las negritas (no uses **asteriscos**).
    6. Deja espacio visual entre conceptos mediante <br>.
    7. No uses este tipo de formato: [guía de compra](https://www.colchones.es/sobre-como-comprar.php), tienes que maquetarlo así: <a href='https://www.colchones.es/sobre-como-comprar.php' target='_blank'>guía de compra</a>
    8. No uses el término 'guía de compra', es preferible que uses 'información del proceso de compra' """
    
    sys_prompt += "\nINSTRUCCIÓN FINAL DE RENDERIZADO:"
    sys_prompt += "\nSi una herramienta te devuelve código HTML (etiquetas <a>, <div>, <img>), TU ÚNICA TAREA ES COPIAR Y PEGAR ESE CÓDIGO HTML TAL CUAL EN TU RESPUESTA."
    sys_prompt += "\nNO lo conviertas a Markdown."

    # 2. CHAT CON OPENAI
    
    messages = [{"role": "system", "content": sys_prompt}] + historial + [{"role": "user", "content": input_data.message}]

    try:
        kwargs = {
            "model": "gpt-4o",
            "messages": messages,
            "temperature": 0.1,       # <--- CAMBIO CRÍTICO: Cero creatividad
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
            print(f"El LLM ha elegido la herramienta: {name}")
            args = json.loads(tool_call.function.arguments)
            res_tool = ""

            if name == "recomendar_colchon":
                res_tool = logica_recomendar_colchon(args, input_data.user_id)
            elif name == "buscar_accesorios_xml":
                res_tool = logica_buscar_accesorios(args, input_data.user_id)
            elif name == "consultar_producto_actual":
                res_tool = logica_consultar_producto_actual(input_data.html_contenido, input_data.user_id)
            elif name == "buscar_info_general":
                res_tool, _sources = get_context_embeddings(input_data.message)
                if _sources:
                    res_tool = f"{res_tool} \n\n(Indica al usuario que puede consultar la siguiente fuente para obtener más información: https://www.colchones.es{_sources[0]})"
            
            messages.append(msg_ia)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": res_tool})
            
            final = client.chat.completions.create(model="gpt-4o", messages=messages)
            respuesta_final = final.choices[0].message.content
        else:
            print("no usa herramientas")
            respuesta_final = msg_ia.content

        guardar_interaccion({
            'user_id': input_data.user_id, 'pregunta': input_data.message, 'respuesta': respuesta_final,
            'url': input_data.url, 'dominio': input_data.dominio, 'articulo_id': input_data.articulo_id, 'nombre_producto': input_data.nombre_producto
        })
        return {"response": respuesta_final}

    except Exception as e:
        guardar_interaccion({
            'user_id': input_data.user_id, 'pregunta': input_data.message, 'respuesta': "Error Api",
            'url': input_data.url, 'dominio': input_data.dominio, 'articulo_id': input_data.articulo_id, 'nombre_producto': input_data.nombre_producto
        })
        traceback.print_exc()
        
        return {"response": f"Ahora mismo no puedo responder preguntas por problemas técnicos. Pero puedes dejarnos un correo o teléfono para poder contactar contigo: <div class='bloqueLeadChati'>        <input type='text' placeholder='Correo o teléfono' style='width:85%; padding:8px;' name='telefonoCorreoCliente' id='telefonoCorreoCliente'/>        <input type='hidden' name='cookieUsuario' id='cookieUsuario' value='{input_data.user_id}'/>     <input type='hidden' name='articuloVisitado' id='articuloVisitado' value='{input_data.articulo_id}'/> <button type='button' style='padding: 10px 9px;    cursor: pointer;    background: #4c9b9d;    float: right;    border: solid 1px #4c9b9d;' onclick='enviarContactoChati()' id='botonEnviarContactoChati'>Enviar</button></div>"}