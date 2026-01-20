# ejecuta con python3.12 sin problemas (3.14 tenía problemas con algunas dependencias)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import html
import os

try:
    # Intento 1: Cuando se llama desde main.py
    from rag.src.colchones_rag import get_embeddings_model, configuration, separators as chunksSeparators
except (ImportError, ModuleNotFoundError):
    # Intento 2: Cuando ejecutas este archivo directamente
    from colchones_rag import get_embeddings_model, configuration, separators as chunksSeparators

load_dotenv()

default_urls = [
    "sobre-como-comprar.php", "sobre-formas-de-pago.php", "pagina-segura.php",
    "sobre-envio-recepcion-pedido.php", "sobre-devoluciones.php", 
    "sobre-condiciones-generales.php", "colchones-on-line-atencion-cliente.php",
    "como-dormir-bien.php", "como-elegir-un-colchon-y-base.php",
    "informacion/mejores-colchones-ocu-2025/", "compromisos.php", "sobre-garantias.php"
]

#def generar_embedding(document):
#    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=separators)
#    texts = text_splitter.split_text(document)
#    print(f"Se han generado {len(texts)} chunks de texto.")
#
#    Chroma.from_texts(
#        texts=texts,
#        embedding=get_embeddings_model(),
#        collection_name=configuration["collection_name"],
#        persist_directory=configuration["persist_dir"],
#        )

# url_pagina es la key para identificar los chunks en la base de datos
def generar_embedding(document, url_pagina):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=chunksSeparators)
    texts = text_splitter.split_text(document)
    
    # Creamos metadatos para cada chunk para poder identificarlos después
    metadatas = [{"source": url_pagina} for _ in range(len(texts))]
    
    # Generamos IDs únicos para cada chunk (ej: "sobre-como-comprar.php_0", "sobre-como-comprar.php_1"...)
    ids = [f"{url_pagina}_{i}" for i in range(len(texts))]

    # Inicializamos el vectorstore
    vectorstore = Chroma(
        collection_name=configuration["collection_name"],
        embedding_function=get_embeddings_model(),
        persist_directory=configuration["persist_dir"]
    )

    # PASO CLAVE: Borramos los registros existentes de esta URL antes de insertar los nuevos
    # Esto simula un "upsert" y evita duplicados si el contenido cambió o se movió de chunk
    try:
        vectorstore.delete(ids=ids) # Intenta borrar IDs específicos si ya existían
        # Opcional: vectorstore._collection.delete(where={"source": url_pagina}) 
    except Exception:
        pass 

    # Añadimos los nuevos textos con sus IDs y metadatos
    vectorstore.add_texts(
        texts=texts,
        metadatas=metadatas,
        ids=ids
    )

def limpiar_html(texto_sucio):
    if not texto_sucio:
        return ""

    # 1. Corregir errores de codificación (Moji-bake: VÃ\xaddeos -> Vídeos)
    try:
        texto = texto_sucio.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        texto = texto_sucio

    # 2. Decodificar entidades HTML (&eacute; -> é)
    texto = html.unescape(texto)

    # 3. Procesar con BeautifulSoup para manejar bloques
    soup = BeautifulSoup(texto, "html.parser")

    # Definimos las etiquetas que queremos que generen un salto de línea
    tags_bloque = ['p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'tr']
    
    for tag in soup.find_all(tags_bloque):
        # Añadimos un espacio/salto al final del contenido de la etiqueta
        tag.append('\n')

    # Extraemos el texto
    texto_plano = soup.get_text()

    # 4. Limpieza final de espacios
    # Eliminamos espacios en blanco al inicio/final de cada línea y 
    # evitamos que se acumulen más de dos saltos de línea seguidos
    lineas = [linea.strip() for linea in texto_plano.splitlines()]
    texto_final = "\n".join(linea for linea in lineas if linea)

    return texto_final

def obtener_embeddings(urls=None):
    try:
        # Si la función ha sido llamada sin argumentos, coge las url por defecto
        if urls is None:
            urls = default_urls
        # Si se le ha pasado una única url y no es una lista, crea una lista con esa única URL
        elif isinstance(urls, str):
            urls = [urls]

        # Configuración de la conexión (vía túnel SSH)
        connection = mysql.connector.connect(
            host='127.0.0.1',
            port=3306, 
            user=os.getenv('mysql_user'),
            password=os.getenv('mysql_pass'),
            database='colchones'
        )

        if connection.is_connected():
            cursor = connection.cursor(dictionary=True) # Para obtener resultados como dict
            cursor.execute("SET SESSION group_concat_max_len = 2000000;")            

            # La consulta con JOINs
            query = """
                SELECT url , concat(group_concat(if(titulo1 <> "", concat(titulo1, " " , m.texto), concat(h1, " " , m.texto))), group_concat(cont.texto, " " , "\n")) as textoPagina
                FROM my_colchoneses_paginas_modulos m
                JOIN my_colchoneses_paginas_modulos_grupo gr on m.id = gr.id_pagina_marca 
                JOIN my_colchoneses_paginas_modulos_contenido cont on gr.id = cont.id_marca_grupo_aj 
                WHERE url in ({})
                GROUP BY url ;
            """.format(','.join(['%s'] * len(urls))) # Crea los placeholders %s dinámicamente

            cursor.execute(query, urls)
            resultados = cursor.fetchall()

            print(f"Se encontraron {len(resultados)} registros:\n")
            for fila in resultados:
                url_actual = fila["url"]
                texto_limpio = limpiar_html(fila["textoPagina"])
                generar_embedding(texto_limpio, url_actual)

    except Error as e:
        print(f"Error al conectar a MySQL: {e}")
    
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("\nConexión cerrada.")
        
        ruta_config = configuration["persist_dir"]
        ruta_absoluta = os.path.abspath(ruta_config)
        print(f"Embeddings guardados en {ruta_absoluta}")

if __name__ == "__main__":
    obtener_embeddings()