from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from dotenv import load_dotenv
import os

load_dotenv()

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
    os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    embeddings_model = OpenAIEmbeddings(
        model="text-embedding-3-small"
        #model="text-embedding-3-large" 
    )

    return embeddings_model

vectorstore = Chroma(
    collection_name = configuration["collection_name"],
    persist_directory = configuration["persist_dir"],
    embedding_function = get_embeddings_model(),
)

def get_context_embeddings(pregunta: str):
    docs = vectorstore.similarity_search_with_relevance_scores(pregunta, k=3)

    try:
        docs = sorted(docs, key=lambda pair: pair[1], reverse=True)
    except Exception:
        pass

    if configuration["debug"]:
        print(f"Para la pregunta '{pregunta}' se han recuperado los siguientes documentos:")
        for i, (d, similarity) in enumerate(docs):
            print(f"Documento {i+1} (similaridad {similarity}): {d.page_content}...")
    
    context = "\n\n".join(d.page_content for (d, _) in docs).strip()
    sources = [doc.metadata.get("source") for (doc, _) in docs]
    sources = [("/" + s) if not s.startswith("http") else s for s in sources]
    return (context, sources)
