from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from colchones_rag import configuration
from colchones_rag import get_context_embeddings
from conversation_history import ConversationHistoryManager

# Create a ConversationHistoryManager and a default global store
history_manager = ConversationHistoryManager(base_dir=configuration["histories_dir"])

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

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0
)

#retriever = vectorstore.as_retriever(
#    search_type="similarity", 
#    search_kwargs={"k": 5} #devuelve los 5 chunks más similares para incorporarlos al contexto
#    )

def answer_question(pregunta: str, user_id: str = "default", history_items: int = 10) -> str:
    """Responder a una pregunta usando el RAG, actualizar el historial y devolver el texto.
    Args:
        pregunta (str): La pregunta del usuario.
        user_id (str, optional): Identificador del usuario para el historial.
        history_items (int, optional): Número de entradas del historial a incluir en el prompt
    """
  
    user_history = history_manager.get(user_id)
    user_history.add_user(pregunta)

    context, _sources = get_context_embeddings(pregunta)

    # Renderizar las últimas entradas del historial para inyectarlas en el prompt
    rendered_history = user_history.render_for_prompt(n=history_items)

    formatted = prompt.format(contexto=context, pregunta=pregunta, chat_history=rendered_history)
    response = llm.invoke(formatted).content

    # Guardar la respuesta en el historial
    user_history.add_assistant(response)

    return response

