from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from colchones_rag import get_embeddings_model
from colchones_rag import configuration

separators = [
    "\n\n",
    "\n",
    "."
]

def main():
    filepath = "document.txt"
    with open(filepath, "r", encoding="utf-8") as file:
        document = file.read()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200, separators=separators)
        texts = text_splitter.split_text(document)
        print(f"Se han generado {len(texts)} chunks de texto.")

        Chroma.from_texts(
            texts=texts,
            embedding=get_embeddings_model(),
            collection_name=configuration.collection_name,
            persist_directory=configuration.persist_dir,
        )



if __name__ == "__main__":
    main()