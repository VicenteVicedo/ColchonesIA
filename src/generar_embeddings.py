from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import html
import os

from colchones_rag import get_embeddings_model
from colchones_rag import configuration

load_dotenv()

separators = [
    "\n\n",
    "\n",
    "."
]

def generar_embedding(document):
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=separators)
    texts = text_splitter.split_text(document)
    print(f"Se han generado {len(texts)} chunks de texto.")

    Chroma.from_texts(
        texts=texts,
        embedding=get_embeddings_model(),
        collection_name=configuration["collection_name"],
        persist_directory=configuration["persist_dir"],
        )

#if __name__ == "__main__":
#    main()

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

def ejecutar_consulta_colchones():
    try:
        # Configuración de la conexión (vía túnel SSH)
        connection = mysql.connector.connect(
            host='127.0.0.1',    # Localhost porque usas el túnel
            port=3306,           # El puerto local del túnel
            user=os.getenv('mysql_user'),
            password=os.getenv('mysql_pass'),
            database='colchones'
        )

        if connection.is_connected():
            cursor = connection.cursor(dictionary=True) # Para obtener resultados como dict
            cursor.execute("SET SESSION group_concat_max_len = 2000000;")
            # Definimos la lista de URLs
            urls = [
                "sobre-como-comprar.php", "sobre-formas-de-pago.php", "pagina-segura.php",
                "sobre-envio-recepcion-pedido.php", "sobre-devoluciones.php", 
                "sobre-condiciones-generales.php", "colchones-on-line-atencion-cliente.php",
                "como-dormir-bien.php", "como-elegir-un-colchon-y-base.php",
                "informacion/mejores-colchones-ocu-2025/", "compromisos.php", "sobre-garantias.php"
            ]

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
                print(limpiar_html(fila["textoPagina"]))
                generar_embedding(limpiar_html(fila["textoPagina"]))

    except Error as e:
        print(f"Error al conectar a MySQL: {e}")
    
    finally:
        if 'connection' in locals() and connection.is_connected():
            cursor.close()
            connection.close()
            print("\nConexión cerrada.")

if __name__ == "__main__":
    ejecutar_consulta_colchones()