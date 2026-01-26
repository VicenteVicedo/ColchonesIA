# Módulo: limpieza y entrenamiento

Este archivo explica cómo usar los scripts dentro de `src/modulos` para preparar las encuestas y entrenar los modelos.

Requisitos
- Python 3.10+ recomendado
- Instalar dependencias del proyecto (desde la raíz del repo):

```bash
pip install -r requirements.txt
```

Nota: los scripts usan `pandas`, `numpy`, `scikit-learn` y `joblib`.

Ficheros relevantes
- `encuestas_colchones.csv` — CSV raw con las encuestas (input).
- `preparar_encuestas.py` — script que limpia y transforma `encuestas_colchones.csv` generando `encuestas_limpio.csv`.
- `entrenar_modelos.py` — carga `encuestas_limpio.csv`, entrena dos modelos (satisfacción y mejora de molestias) y guarda:
  - `modelo_satisfaccion.pkl`
  - `modelo_mejoras.pkl`

Instrucciones (paso a paso)
1. Colocarse en el directorio del módulo (opcional, los scripts usan paths relativos):

```bash
cd src/modulos
```

2. Generar el CSV limpio desde el CSV original

```bash
python preparar_encuestas.py
```

Salida esperada:
- `encuestas_limpio.csv` (archivo CSV generado en `src/modulos`).
- Logs por consola indicando número de filas.

3. Entrenar los modelos

```bash
python entrenar_modelos.py
```

Salida esperada:
- `modelo_satisfaccion.pkl`
- `modelo_mejoras.pkl`
- Mensajes por consola indicando progreso y guardado de modelos.

Consejos y notas
- Los scripts asumen que los CSVs están en el mismo directorio desde el cual se ejecutan. Si ejecutas desde la raíz del repo, asegúrate de ajustar rutas o de pasar al directorio `src/modulos`.
- Si falta alguna columna en `encuestas_colchones.csv`, revisa primero con `verColumnas.py` para inspeccionar nombres y limpieza.
- Para entornos reproducibles crea un `venv` o usa `conda`.

Ejemplo rápido (Windows / PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd src/modulos
python preparar_encuestas.py
python entrenar_modelos.py
```

Problemas comunes
- Errores de lectura CSV: abre el fichero con Excel/Editor y verifica separadores y encabezados.
- Errores de dependencias: instala las versiones recomendadas de `pandas` y `scikit-learn` desde `requirements.txt`.

Si quieres, puedo añadir un pequeño script `run_all.sh` / `run_all.ps1` para automatizar estos pasos.
