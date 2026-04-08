import os
import sys

# 1. PRIMERO configuramos el path
# Esto le dice a Python que mire en la carpeta raíz 'sentinel'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 2. DESPUÉS importamos tus módulos
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.agent.agent import get_llm, run_agent

app = FastAPI()

# 1. Configurar CORS (Vital para que el HTML pueda llamar a la API)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permite peticiones desde cualquier origen
    allow_credentials=True,
    allow_methods=["*"], # Permite todos los métodos (POST, GET, etc.)
    allow_headers=["*"], # Permite todas las cabeceras
)

# Modelo para el chat
class ChatQuery(BaseModel):
    question: str

# Modelo para la configuración del modelo
class ConfigQuery(BaseModel):
    mode: str

# 2. Servir el archivo index.html en la raíz
@app.get("/")
def read_index():
    # Buscamos el archivo index.html que está en la carpeta /chatbot
    path = os.path.join(os.getcwd(), "chatbot", "index.html")
    return FileResponse(path)

@app.post("/chat")
def chat(query: ChatQuery):
    response = run_agent(query.question)
    return {"response": response}

@app.post("/config-model")
def config_model(config: ConfigQuery):
    # Llamamos a la función que reconstruye el agente
    get_llm(config.mode)
    return {"status": "success", "model_active": config.mode}