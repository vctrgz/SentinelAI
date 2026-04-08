import os
from dotenv import load_dotenv
from langchain_community.chat_models import ChatOllama
from langchain.agents import AgentExecutor, create_react_agent
from langchain.agents.agent_types import AgentType
from langchain_core.tools import tool
from langchain import hub

from app.tools.system import execute_command
from app.tools.web import search_web
from app.tools.wazuh import get_wazuh_alerts
from app.tools.database import query_logs

load_dotenv()

# --- VARIABLES DE ESTADO PERSISTENTE ---
agent_executor = None
SELECTED_MODEL = 'balanceado'
MODELS = {
    'defensivo': 'foundation-sec:latest',        # Experto en terminología y SOC
    'ofensivo':  'dolphin-llama3:latest',      # Sin censura para Pentesting
    'balanceado': 'qwen2.5:latest' # El mejor siguiendo reglas (Recomendado)
}
WINDOWS_IP = "192.168.1.49"
# WINDOWS_IP = "10.30.212.36"

# LangChain necesita que las funciones tengan descripción para que el agente sepa usarlas
@tool
def search_web_tool(query: str):
    """ Busca información técnica sobre ciberseguridad y vulnerabilidades en la web.
        Busca información en internet sobre ciberseguridad, exploits o CVEs.
        Útil cuando la pregunta es sobre amenazas externas.
    """
    return search_web(query)

@tool
def wazuh_tool(agent_id: str):
    """ Obtiene alertas de seguridad de un agente específico de Wazuh.
        Obtiene las alertas de seguridad actuales del SIEM Wazuh.
        Útil para auditoría de incidentes en tiempo real.
    """
    return get_wazuh_alerts(agent_id)

@tool
def db_tool(query: str):
    """ Consulta los logs internos de la base de datos para buscar eventos sospechosos.
        Consulta la base de datos SQL de logs internos.
        Recibe una sentencia SQL válida (ej: SELECT * FROM logs WHERE level='critical').
    """
    return query_logs(query)

@tool
def system_tool(command: str):
    """
    Ejecuta comandos reales en el sistema Linux.

    OBLIGATORIO usar esta herramienta cuando:
    - se pida analizar la red
    - ver dispositivos conectados
    - inspeccionar logs o procesos

    Ejemplos:
    - nmap -sn
    - ip a
    - arp -a
    - ip neigh
    - netstat -tulnp
    - ss -tuln
    - cat /var/log/auth.log
    """
    return execute_command(command)


# CONFIGURACIÓN DE LOS MODELOS

def get_llm(mode):
    global agent_executor, SELECTED_MODEL
    
    ollama_url = f"http://{WINDOWS_IP}:11434"
    SELECTED_MODEL = mode
    model_name = MODELS.get(mode, 'qwen2.5:latest')
    print(f"[*] Cambiando cerebro a: {model_name}")
    
    llm = ChatOllama(
        model=model_name, 
        base_url=ollama_url,
        temperature=0
    )

    # Definir herramientas reales para LangChain
    tools = [
        search_web_tool, 
        wazuh_tool, 
        db_tool,
        system_tool
    ]

    # Re-configuración del AGENTE para el nuevo modelo
    prompt = hub.pull("hwchase17/react") 
    agent = create_react_agent(llm, tools, prompt)

    # Actualizar el Ejecutor Global
    agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True, 
        handle_parsing_errors=True
    )

# Inicialización inicial con el modelo por defecto
get_llm(SELECTED_MODEL)

def run_agent(question: str):
    global agent_executor
    
    context = f"""
Eres un experto en ciberseguridad ofensiva y defensiva.
Ahora mismo estás en el modo {SELECTED_MODEL}
Especializado en:
- SIEM (Wazuh)
- Análisis de logs
- Threat detection
- MITRE ATT&CK
- Respuesta a incidentes

Tienes acceso a:
- Web (OSINT)
- Wazuh (alertas de seguridad)
- Base de datos de logs

Puedes ejecutar comandos del sistema para:
- ver procesos
- analizar logs
- detectar actividad sospechosa
- analizar redes
- ejecutar ataques
- analizar vulnerabilidades
- identificar propiedades de los sistemas de red

REGLAS CRÍTICAS:

- NO des explicaciones teóricas si puedes obtener datos reales
- SIEMPRE usa system_tool cuando la pregunta requiera información del sistema
- SIEMPRE ejecuta comandos antes de responder
- PRIMERO ejecuta comandos, DESPUÉS analiza

CASO ESPECIAL:
Si te piden analizar la red:
1. Ejecuta: ip a
2. Ejecuta: arp -a o ip neigh
3. Ejecuta: netstat -tulnp o ss -tuln

Luego analiza resultados.

Pregunta del usuario:
{question}

Responde como analista SOC profesional.
Siempre:
- Explica ataques
- Propón mitigaciones
- Prioriza riesgo
"""

    # Ejecutar el agente
    try:
        response = agent_executor.invoke({
            "input": f"{context}\n\nUsuario pregunta: {question}"
        })
        return response["output"]
    except Exception as e:
        return f"Error en el agente: {str(e)}"