from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
import os

configuration = {
    "persist_dir": "./embeddings_db",
    "collection_name": "colchones_rag",
    "histories_dir": "./histories",
    "debug": True
}

separators = [
    "\n\n",
    "\n",
    "."
]

def get_embeddings_model():
    os.environ["OPENAI_API_KEY"] = "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"
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small" #Tiene que ser el mismo modelo para generar los embeddings y para hacer las consultas
        # or "text-embedding-3-large" 
    )

    return embeddings

vectorstore = Chroma(
    collection_name = configuration["collection_name"],
    persist_directory = configuration["persist_dir"],
    embedding_function = get_embeddings_model(),
)

def get_context_embeddings(pregunta: str):
    docs = vectorstore.similarity_search_with_relevance_scores(pregunta)
    if configuration["debug"]:
        print(f"Para la pregunta '{pregunta}' se han recuperado los siguientes documentos:")
        for i, (d, similarity) in enumerate(docs):
            print(f"Documento {i+1} (similaridad {similarity}): {d.page_content[:200]}...")
    
    context = "\n\n".join(d.page_content for (d, _similarity) in docs).strip()
    return context