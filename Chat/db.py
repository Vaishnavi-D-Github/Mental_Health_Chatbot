# db.py
import os
import json
from pymongo import MongoClient
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
ADMIN_KEY = os.environ.get("ADMIN_KEY")
fernet = Fernet(ADMIN_KEY.encode())

client = MongoClient(MONGO_URI)
db = client["ChatbotDB"]
conversations_col = db["Conversations"]

# Store a single message
def store_message(user_id, conversation_id, role, text):
    # Encrypt message text
    enc_text = fernet.encrypt(text.encode()).decode()
    conversations_col.update_one(
        {"conversation_id": conversation_id},
        {"$push": {"messages": {"role": role, "text": enc_text}}},
        upsert=True
    )

# Fetch conversation messages
def get_conversation(conversation_id):
    doc = conversations_col.find_one({"conversation_id": conversation_id})
    if not doc:
        return {"messages": []}
    # Decrypt messages
    decrypted = []
    for msg in doc["messages"]:
        try:
            decrypted_text = fernet.decrypt(msg["text"].encode()).decode()
            decrypted.append({"role": msg["role"], "text": decrypted_text})
        except Exception:
            decrypted.append({"role": msg["role"], "text": "[decryption error]"})
    return {"messages": decrypted}

