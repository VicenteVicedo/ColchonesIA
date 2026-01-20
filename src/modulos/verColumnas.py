import pandas as pd
import numpy as np

# =========================
# 1. Cargar CSV original
# =========================
df = pd.read_csv("encuestas_original.csv", sep=None, engine="python")

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
    altura_muj_
