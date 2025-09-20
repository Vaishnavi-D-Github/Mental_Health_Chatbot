from db import store_message, get_conversation
from llama_client import call_ollama

def get_llama_response(user_id, conversation_id, user_text, system_prompt=None):
    # Fetch previous conversation
    conv_data = get_conversation(conversation_id)
    context = ""
    if conv_data:
        for msg in conv_data["messages"][-6:]:  # last 6 messages
            context += f"{msg['role'].capitalize()}: {msg['text']}\n"

    context += f"User: {user_text}\n"

    # Include system prompt if provided
    if system_prompt:
        prompt = f"{system_prompt}\n\n{context}Assistant:"
    else:
        prompt = f"{context}Assistant:"

    # Call the LLaMA API
    reply = call_ollama(prompt)

    # Store messages in MongoDB
    store_message(user_id, conversation_id, "user", user_text)
    store_message(user_id, conversation_id, "assistant", reply)

    return reply
