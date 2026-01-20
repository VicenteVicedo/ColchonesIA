recomendar = {
    "type": "function",
    "function": {
        "name": "recomendar_colchon",
        "description": "Calcula el mejor colchón basado en peso/altura.",
        "parameters": {
            "type": "object",
            "properties": {
                "sexo": {"type": "string", "enum": ["hombre", "mujer"]},
                "altura": {"type": "number"},
                "peso": {"type": "number"},
                "duerme_en_pareja": {"type": "boolean"},
                "molestias_antes": {"type": "boolean"},
                "material_preferido": {"type": "string", "enum": ["muelles", "viscoelastica", "latex", "espuma"]}
            },
            "required": ["sexo", "altura", "peso"]
        }
    }
}

buscar_accesorios = {
    "type": "function",
    "function": {
        "name": "buscar_accesorios_xml",
        "description": "Busca almohadas, canapés, bases o ropa de cama por palabra clave.",
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {"type": "string", "description": "Palabras clave (ej: 'almohada visco')"}
            },
            "required": ["keywords"]
        }
    }
}

consultar_ficha = {
    "type": "function",
    "function": {
        "name": "consultar_producto_actual",
        "description": "Lee la ficha técnica del producto que el usuario está viendo ahora mismo.",
        "parameters": {
            "type": "object", 
            "properties": {}, 
            "required": []
        }
    }
}


rag_datos_generales_tienda = {
    "type": "function",
    "function": {
        "name": "buscar_info_general",
        "description": "Información general sobre la tienda de colchones (sobre-como-comprar, sobre-formas-de-pago, sobre-envio-recepcion-pedido, -atencion-cliente, como-dormir-bien, como-elegir-un-colchon-y-base, mejores-colchones-ocu-2025, compromisos de nuestra web, sobre-garantias)",
        "parameters": {
            "type": "object",
            "properties": {"pregunta": {"type": "string"}},
            "required": ["pregunta"]
        }
    }
}