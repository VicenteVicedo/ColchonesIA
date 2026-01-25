# ejecuta con python3.12 sin problemas (3.14 tenía problemas con algunas dependencias)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from bs4 import BeautifulSoup

import os

try:
    # Intento 1: Cuando se llama desde main.py
    from rag.src.colchones_rag import get_embeddings_model, configuration, separators as chunksSeparators
    from rag.src.scrap_url import obtener_contenido_url
    from rag.src.scrap_url import preprocesar_html
except (ImportError, ModuleNotFoundError):
    # Intento 2: Cuando ejecutas este archivo directamente
    from scrap_url import obtener_contenido_url
    from scrap_url import preprocesar_html
    from colchones_rag import get_embeddings_model, configuration, separators as chunksSeparators

load_dotenv()

default_urls = [
    "sobre-como-comprar.php", "sobre-formas-de-pago.php", "pagina-segura.php",
    "sobre-envio-recepcion-pedido.php", "sobre-devoluciones.php", 
    "sobre-condiciones-generales.php", "colchones-on-line-atencion-cliente.php",
    "como-dormir-bien.php", "como-elegir-un-colchon-y-base.php",
    "informacion/mejores-colchones-ocu-2025/", "compromisos.php", "sobre-garantias.php",

    "firmeza-del-colchon.php",
    "medidas-de-colchones.php","tipos-de-colchones.php","colchones-estilos-de-vida.php",
    "consejos-colchon-latex.php","consejos-colchon-viscoelastica.php","consejos-limpiar-cambiar-colchon.php",
    "como-elegir-un-colchon-y-base/composicion-somier-laminas.php",
    "como-elegir-un-colchon-y-base/estructura-canapes-y-tapas.php",
    "como-elegir-un-colchon-y-base/sistemas-apertura-canapes.php",
    "informacion/fibromialgia-o-fatiga-cronica-y-el-colchon-mas-adecuado/"
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
        collection_name=configuration.get("collection_name"),
        embedding_function=get_embeddings_model(),
        persist_directory=configuration.get("persist_dir")
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
    print(f"Se han generado {len(texts)} chunks de texto para la URL {url_pagina}.")


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
            host=os.getenv('BBDD_IP'),
            port=os.getenv('BBDD_PORT'), 
            user=os.getenv('mysql_user'),
            password=os.getenv('mysql_pass'),
            database=os.getenv('BBDD_NAME')
        )

        if connection.is_connected():
            cursor = connection.cursor(dictionary=True) # Para obtener resultados como dict
            cursor.execute("SET SESSION group_concat_max_len = 2000000;")            

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

            # Si la página no está en la base de datos, intentar obtener su contenido vía scrapping
            try:
                if len(resultados) == 0 and len(urls) == 1:
                    print(f"La URL {urls[0]} no se encontró en la base de datos. Intentando vía scrapping...")
                    contenido_pagina = obtener_contenido_url(urls[0])
                    generar_embedding(contenido_pagina, urls[0])
                else:
                    print(f"Se encontraron {len(resultados)} registros:\n")
                    for fila in resultados:
                        url_actual = fila["url"]
                        texto_limpio = preprocesar_html(fila["textoPagina"])
                        generar_embedding(texto_limpio, url_actual)

            except Exception as e:
                print(f"Error al obtener embeddings : {e}")

            

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