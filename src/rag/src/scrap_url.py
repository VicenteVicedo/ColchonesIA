from bs4 import BeautifulSoup
import html

def preprocesar_html(html_sin_procesar, tags=None, min_length=None) -> str:
    if not html_sin_procesar:
        return ""

    # 1. Corregir errores de codificación (Moji-bake: VÃ\xaddeos -> Vídeos)
    try:
        texto = html_sin_procesar.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        texto = html_sin_procesar

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
    if tags:
        # Si se especifican etiquetas, extraemos solo su contenido
        partes = []
        for etiqueta in tags:
            for el in soup.find_all(etiqueta):
                if min_length and len(el.get_text()) >= min_length:
                    partes.append(el.get_text())
        texto_plano = "\n".join(partes)
    
    else:
        texto_plano = soup.get_text()

    # 4. Limpieza final de espacios
    # Eliminamos espacios en blanco al inicio/final de cada línea y 
    # evitamos que se acumulen más de dos saltos de línea seguidos
    lineas = [linea.strip() for linea in texto_plano.splitlines()]
    texto_final = "\n".join(linea for linea in lineas if linea)

    return texto_final

def obtener_pagina_scrapping(url: str, section_id: str = 'content') -> str:
    # Construir URL completa si es relativa
    if not url.startswith("http://") and not url.startswith("https://"):
        base = "https://colchones.es"
        # asegurar slash entre base y ruta
        if base.endswith("/") and url.startswith("/"):
            full_url = base[:-1] + url
        elif not base.endswith("/") and not url.startswith("/"):
            full_url = base + "/" + url
        else:
            full_url = base + url
    else:
        full_url = url

    html_text = None
    # Intentar con requests si está instalado
    try:
        import requests

        resp = requests.get(full_url, timeout=15)
        resp.raise_for_status()
        html_text = resp.text
    except Exception:
        # Fallback a urllib
        try:
            from urllib.request import urlopen

            with urlopen(full_url, timeout=15) as f:
                bytes_content = f.read()
                # intentar detección simple de encoding
                try:
                    html_text = bytes_content.decode("utf-8")
                except Exception:
                    try:
                        html_text = bytes_content.decode("latin-1")
                    except Exception:
                        html_text = bytes_content.decode(errors="ignore")
        except Exception:
            return ""

    if not html_text:
        return ""

    # Parsear y extraer la sección si se pide
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        if section_id:
            el = soup.find(id=section_id)
            if el:
                return str(el)
            else:
                el = soup.find(id='centro')
                if el:
                    return str(el)
                else:
                    return ""
        # Si no piden sección, devolver el HTML completo
        return str(soup)
    except Exception as e:
        print(f"Error al parsear HTML de {full_url}: {e}")
        return ""

def obtener_contenido_url(url: str) -> str:
    html_content = obtener_pagina_scrapping(url)
    texto_limpio = preprocesar_html(html_content, ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"])
    return texto_limpio

# Si se ejecuta este script directamente, hacer una prueba rápida
if __name__ == "__main__":
    urls = ["https://www.colchones.es/rebajas-ofertas-descuentos-promociones.php","https://www.colchones.es/firmeza-del-colchon.php","https://www.colchones.es/medidas-de-colchones.php","https://www.colchones.es/tipos-de-colchones.php","https://www.colchones.es/colchones-estilos-de-vida.php","https://www.colchones.es/consejos-colchon-latex.php","https://www.colchones.es/consejos-colchon-viscoelastica.php","https://www.colchones.es/consejos-limpiar-cambiar-colchon.php","https://www.colchones.es/como-elegir-un-colchon-y-base/composicion-somier-laminas.php","https://www.colchones.es/como-elegir-un-colchon-y-base/estructura-canapes-y-tapas.php","https://www.colchones.es/como-elegir-un-colchon-y-base/sistemas-apertura-canapes.php","https://www.colchones.es/informacion/fibromialgia-o-fatiga-cronica-y-el-colchon-mas-adecuado/"]

    for url in urls:
        contenido = preprocesar_html(obtener_pagina_scrapping(url), ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"], 50)
        print(f"Contenido extraído de {url}:\n{contenido}...\n\n")
        input("Presiona Enter para continuar...")
