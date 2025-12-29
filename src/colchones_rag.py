from langchain_openai import OpenAIEmbeddings
import os

def get_embeddings_model():
    os.environ["OPENAI_API_KEY"] = "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"
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small"
        # or "text-embedding-3-small" for cheaper/faster
    )

    return embeddings


configuration = {
    "persist_dir": "./embeddings_textos.chroma_db",
    "collection_name": "colchones_rag"
}