import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
import joblib

# ==========================
# 1. Cargar CSV limpio
# ==========================
df = pd.read_csv("encuestas_limpio.csv")
print("Filas cargadas:", len(df))

# ==========================================
# 2. Crear variable objetivo para mejoras de molestias
# ==========================================
df["mejora_molestias"] = np.where(
    (df["molestias_antes"] == 1) & (df["molestias_despues"] == 0),
    1,
    0
)

# ==========================
# 3. Variables de entrada
# ==========================
feature_cols = [
    "sexo",
    "altura",
    "peso",
    "imc",
    "duerme_en_pareja",
    "nucleo",
    "grosor",
    "firmeza",
    "molestias_antes"
]

X = df[feature_cols]

# Objetivos
y_satisf = df["valoracion"]
y_mejoras = df["mejora_molestias"]

# ==========================================
# 4. Preprocesamiento (OneHotEncoder)
# ==========================================
cat_cols = ["sexo", "nucleo", "grosor"]
num_cols = ["altura", "peso", "imc", "duerme_en_pareja", "firmeza", "molestias_antes"]

preprocessor = ColumnTransformer(
    transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
        ("num", "passthrough", num_cols)
    ]
)

# ==========================
# 5. MODELO 1 → Satisfacción
# ==========================
modelo_satisf = Pipeline(steps=[
    ("preprocess", preprocessor),
    ("model", RandomForestRegressor(
        n_estimators=300,
        max_depth=12,
        random_state=42,
        n_jobs=-1
    ))
])

print("Entrenando modelo de satisfacción…")
modelo_satisf.fit(X, y_satisf)

joblib.dump(modelo_satisf, "modelo_satisfaccion.pkl")
print("Guardado modelo_satisfaccion.pkl")

# ==========================
# 6. MODELO 2 → Mejora molestias
# ==========================
modelo_mejoras = Pipeline(steps=[
    ("preprocess", preprocessor),
    ("model", RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        random_state=42,
        n_jobs=-1
    ))
])

print("Entrenando modelo de mejora de molestias…")
modelo_mejoras.fit(X, y_mejoras)

joblib.dump(modelo_mejoras, "modelo_mejoras.pkl")
print("Guardado modelo_mejoras.pkl")

print("\n=== ENTRENAMIENTO COMPLETADO CON RANDOM FOREST ===")
