import re
from bs4 import BeautifulSoup

def parsear_html_a_markdown(html_content):
    """
    Recibe un string con código HTML crudo.
    1. Busca el contenedor principal (id='centro').
    2. Limpia basura (scripts, estilos).
    3. Convierte etiquetas clave a Markdown (#, |, -, **).
    4. Devuelve un string limpio y estructurado.
    """
    if not html_content:
        return "Error: HTML vacío."

    try:
        # Usamos lxml si es posible por velocidad, sino el parser estándar
        soup = BeautifulSoup(html_content, 'html.parser')

        # 1. ENFOQUE QUIRÚRGICO: Buscar solo id="centro"
        # Si tu web cambia de layout, aquí puedes añadir 'main' o 'center_column'
        contenido_principal = soup.find(id="centro")

        if not contenido_principal:
            # Fallback: Si no encuentra #centro, intenta buscar #main o coge el body entero
            contenido_principal = soup.find("main") or soup.find("body") or soup

        # 2. LIMPIEZA INTERNA (Solo dentro del centro)
        # Eliminamos ruido que confunde a la IA
        etiquetas_borrar = [
            'script', 'style', 'iframe', 'form', 'noscript', 
            'input', 'button', 'select', 'textarea', 'svg', 'nav', 'footer'
        ]
        for tag in contenido_principal(etiquetas_borrar):
            tag.decompose()

        # 3. TRANSFORMACIÓN A MARKDOWN (Inyección de símbolos)

        # A. Títulos (H1-H6) -> #, ##, ...
        for i in range(1, 7):
            for tag in contenido_principal.find_all(f'h{i}'):
                prefix = '#' * i
                # Añadimos saltos de línea para separar secciones
                tag.insert_before(f"\n\n{prefix} ")
                tag.insert_after("\n")

        # B. Tablas -> | Celda | Celda | (Formato Markdown)
        for tr in contenido_principal.find_all('tr'):
            cells = tr.find_all(['td', 'th'])
            if cells:
                # Extraemos texto limpio de cada celda
                row_text = " | ".join([c.get_text(strip=True) for c in cells])
                # Reemplazamos la fila HTML por texto visual
                tr.replace_with(f"\n| {row_text} |\n")

        # C. Listas -> Guiones
        for li in contenido_principal.find_all('li'):
            li.insert_before("\n- ")

        # D. Negritas -> **Texto**
        for tag in contenido_principal.find_all(['strong', 'b']):
            tag.insert_before("**")
            tag.insert_after("**")

        # E. Imágenes -> [FOTO: Alt]
        # Filtramos iconos o imágenes de tracking
        for img in contenido_principal.find_all('img'):
            alt = img.get('alt', 'Imagen')
            src = img.get('src', '')
            
            # Solo mantenemos imágenes que parezcan de producto
            # Evitamos: logos, iconos, spacers, pixels
            es_basura = any(x in src for x in ['icon', 'logo', 'pixel', 'transp', 'arrow', 'star'])
            
            if src and not es_basura:
                img.replace_with(f"\n\n[FOTO: {alt}]\n")
            else:
                img.decompose()

        # F. Enlaces -> Mantenemos solo el texto del enlace, quitamos la URL para no ensuciar
        # (Opcional: Si quieres mantener el link, usa el formato [Texto](URL))
        for a in contenido_principal.find_all('a'):
            a.replace_with(f" {a.get_text(strip=True)} ")

        # 4. EXTRACCIÓN DE TEXTO PURO
        # separator=' ' evita que palabras de distintos divs se peguen
        texto_crudo = contenido_principal.get_text(separator=' ')

        # 5. POST-PROCESADO (Limpieza final de espacios)
        lines = []
        for line in texto_crudo.splitlines():
            clean = line.strip()
            # Filtramos líneas vacías o caracteres sueltos que no aportan nada
            if clean and len(clean) > 1: 
                lines.append(clean)
            elif clean.startswith("|"): # Mantenemos las tablas aunque sean cortas
                lines.append(clean)
        
        texto_final = "\n".join(lines)
        
        # Eliminar dobles espacios generados por la eliminación de tags
        texto_final = re.sub(r' +', ' ', texto_final)
        # Eliminar saltos de línea excesivos (más de 3 seguidos)
        texto_final = re.sub(r'\n{3,}', '\n\n', texto_final)
        
        return texto_final

    except Exception as e:
        return f"Error procesando HTML: {str(e)}"


# ==========================================
# ZONA DE PRUEBAS (Solo se ejecuta si lanzas este fichero)
# ==========================================
if __name__ == "__main__":
    import requests
    
    # URL DE PRUEBA POR DEFECTO
    URL_DEFAULT = "https://www.colchones.es/colchones/juvenil-First-Sac-muelles-ensacados-viscoelastica-fibras/"
    
    print(f"🧪 MODO PRUEBA ACTIVADO")
    print(f"🌍 Descargando HTML de: {URL_DEFAULT} ...")
    
    try:
        # Simulamos un navegador
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0'}
        response = requests.get(URL_DEFAULT, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html_real = response.text
            print("✅ HTML descargado. Procesando...")
            
            # LLAMADA A LA FUNCIÓN PRINCIPAL
            resultado_markdown = parsear_html_a_markdown(html_real)
            
            print("\n" + "="*50)
            print("RESULTADO FINAL (MARKDOWN LIMPIO)")
            print("="*50 + "\n")
            print(resultado_markdown)
            
            print("\n" + "="*50)
            print(f"📊 Estadísticas:")
            print(f"   - Caracteres HTML original: {len(html_real)}")
            print(f"   - Caracteres Markdown final: {len(resultado_markdown)}")
            print(f"   - Reducción de ruido: {100 - (len(resultado_markdown)/len(html_real)*100):.1f}%")
            print("="*50)
            
        else:
            print(f"❌ Error al descargar URL: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error crítico en prueba: {e}")