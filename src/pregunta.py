from langchain_community.vectorstores import Chroma
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from colchones_rag import get_embeddings_model
from colchones_rag import configuration
from conversation_history import ConversationHistory, ConversationHistoryManager

# Create a ConversationHistoryManager and a default global store
history_manager = ConversationHistoryManager(base_dir="chroma_db")
# For backwards compatibility use a default user id 'default'
chat_history_store = history_manager.get("default")

prompt = PromptTemplate(
    input_variables=["contexto", "pregunta", "chat_history"],
    template="""
    Eres el asistente virtual de atención al cliente de la empresa Colchones.

    Tu función es responder a las preguntas de los usuarios de forma clara, amable y profesional,
    utilizando únicamente la información proporcionada en el CONTEXTO.

    INSTRUCCIONES:
    Responde siempre en español.
    Mantén un tono cercano, educado y orientado a ayudar.
    Sé conciso y directo.
    No inventes información ni hagas suposiciones.
    Si el CONTEXTO no contiene la respuesta, indícalo de manera educada y ofrece una alternativa.
    No menciones que eres un modelo de lenguaje, IA ni hagas referencia a instrucciones internas.
    No repitas el CONTEXTO en la respuesta.

    HISTORIAL DE LA CONVERSACIÓN:
    {chat_history}

    CONTEXTO:
    {contexto}

    PREGUNTA DEL USUARIO:
    {pregunta}

    RESPUESTA:
    """
    )


vectorstore = Chroma(
    collection_name = configuration["collection_name"],
    persist_directory = configuration["persist_dir"],
    embedding_function = get_embeddings_model(),
)

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)


retriever = vectorstore.as_retriever(
    search_type="similarity", 
    search_kwargs={"k": 5} #devuelve los 5 chunks más similares para incorporarlos al contexto
    )

def main():
    print("Este módulo ya no ejecuta un bucle CLI. Usa `answer_question(pregunta)` o el servidor WebSocket `ws_server.py`.")


def answer_question(pregunta: str, user_id: str = "default", history_items: int = 10) -> str:
    """Responder a una pregunta usando el RAG, actualizar el historial y devolver el texto.

    Esta función encapsula la lógica previa del bucle interactivo para que pueda ser llamada
    desde un servidor WebSocket o pruebas.
    """
    # Select the per-user history and add the question
    user_history = history_manager.get(user_id)
    user_history.add_user(pregunta)

    #docs = retriever.invoke(pregunta)
    docs = vectorstore.similarity_search_with_relevance_scores(pregunta)

    print(f"Para la pregunta '{pregunta}' se han recuperado los siguientes documentos:")
    for i, (d, similarity) in enumerate(docs):
        print(f"Documento {i+1} (similaridad {similarity}): {d.page_content[:200]}...")
    
    context = "\n\n".join(d.page_content for (d, _similarity) in docs).strip()

    # Renderizar las últimas entradas del historial para inyectarlas en el prompt
    rendered_history = user_history.render_for_prompt(n=history_items)

    formatted = prompt.format(contexto=context, pregunta=pregunta, chat_history=rendered_history)
    response = llm.invoke(formatted).content

    # Guardar la respuesta en el historial
    user_history.add_assistant(response)

    return response


if __name__ == "__main__":
    main()