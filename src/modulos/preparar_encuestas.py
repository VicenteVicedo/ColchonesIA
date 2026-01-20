import pandas as pd
import numpy as np

# =========================
# 1. Cargar CSV original
# =========================
df = pd.read_csv("encuestas_colchones.csv", sep=None, engine="python")

# NORMALIZAR nombres de columnas (por si tienen espacios delante/detrás)
df.columns = [c.strip() for c in df.columns]

print("Columnas detectadas por pandas:")
print(df.columns.tolist())

# ==========================================
# Helpers
# ==========================================
def normalize_bool(x):
    if pd.isna(x):
        return 0
    x = str(x).strip().lower()
    if x in ["si", "sí", "1", "true"]:
        return 1
    return 0

def to_float(x):
    if pd.isna(x):
        return np.nan
    x = str(x).strip().replace(",", ".")
    try:
        return float(x)
    except:
        return np.nan

# ======================================================
# Crear un dataframe vacío para almacenar las nuevas filas
# ======================================================
rows = []

for _, row in df.iterrows():

    # MUJER PRESENTE SI ID MUJER1 NO ES NaN
    id_mujer = row.get("ID MUJER1", np.nan)
    mujer_presente = not pd.isna(id_mujer)

    # HOMBRE PRESENTE SI ID HOMBRE1 NO ES NaN
    id_hombre = row.get("ID HOMBRE1", np.nan)
    hombre_presente = not pd.isna(id_hombre)

    # SI HAY HOMBRE Y MUJER → DUERME EN PAREJA
    duerme_en_pareja = 1 if (mujer_presente and hombre_presente) else 0

    # ------------------------------------------
    # PROCESAR MUJER
    # ------------------------------------------
    altura_mujer = row.get("MUJER1 altura", np.nan)
    if mujer_presente and not pd.isna(altura_mujer):
        rows.append({
            "cod_pedido": row.get("COD PEDIDO"),
            "cod_articulo": row.get("COD ARTICULO"),
            "nombre_articulo": row.get("NOMBRE ARTICULO"),
            "nucleo": row.get("NUCLEO"),
            "grosor": row.get("GROSOR"),
            "firmeza": row.get("FIRMEZA"),
            "sexo": "mujer",
            "altura": to_float(row.get("MUJER1 altura")),
            "peso": to_float(row.get("MUJER1 peso")),
            "imc": to_float(row.get("MUJER1 imc")),
            "valoracion": row.get("MUJER1 VALORACION"),
            "molestias_antes": normalize_bool(row.get("MUJER1 MOLESTIAS ANTES")),
            "molestias_despues": normalize_bool(row.get("MUJER1 MOLESTIAS DESPUES")),
            "duerme_en_pareja": duerme_en_pareja
        })

    # ------------------------------------------
    # PROCESAR HOMBRE
    # ------------------------------------------
    altura_hombre = row.get("HOMBRE1 altura", np.nan)
    if hombre_presente and not pd.isna(altura_hombre):
        rows.append({
            "cod_pedido": row.get("COD PEDIDO"),
            "cod_articulo": row.get("COD ARTICULO"),
            "nombre_articulo": row.get("NOMBRE ARTICULO"),
            "nucleo": row.get("NUCLEO"),
            "grosor": row.get("GROSOR"),
            "firmeza": row.get("FIRMEZA"),
            "sexo": "hombre",
            "altura": to_float(row.get("HOMBRE1 altura")),
            "peso": to_float(row.get("HOMBRE1 peso")),
            "imc": to_float(row.get("HOMBRE1 imc")),
            "valoracion": row.get("HOMBRE1 VALORACION"),
            "molestias_antes": normalize_bool(row.get("HOMBRE1 MOLESTIAS ANTES")),
            "molestias_despues": normalize_bool(row.get("HOMBRE1 MOLESTIAS DESPUES")),
            "duerme_en_pareja": duerme_en_pareja
        })

    # ------------------------------------------
    # NIÑOS: por ahora NO los incluimos (opción recomendada)
    # ------------------------------------------

# ===============================
# Crear dataframe final
# ===============================
df_final = pd.DataFrame(rows)

# Quitar filas sin valoración
df_final = df_final[~df_final["valoracion"].isna()]
df_final["valoracion"] = pd.to_numeric(df_final["valoracion"], errors="coerce")
df_final = df_final[~df_final["valoracion"].isna()]

df_final.to_csv("encuestas_limpio.csv", index=False, float_format="%.3f")

print("\nCSV limpio generado correctamente → encuestas_limpio.csv")
print("Total filas:", len(df_final))
print(df_final.head())
