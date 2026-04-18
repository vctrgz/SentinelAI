import os
from utils.agent_parser import extract_skills
from utils.skill_loader import load_skills


def load_file(path: str) -> str:
    if not os.path.exists(path):
        return ""

    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def build_system_prompt(agent_dir: str) -> str:
    """
    Construye el prompt completo con:
    - AGENTS.md
    - skills dinámicos
    """

    agent_md_path = os.path.join(agent_dir, "AGENTS.md")

    agent_md = load_file(agent_md_path)

    # 🔹 EXTRAER SKILLS
    skills = extract_skills(agent_md_path)

    # 🔹 CARGAR SOLO ESAS SKILLS
    skills_content = load_skills(skills)

    system_prompt = f"""
{agent_md}

---

## AVAILABLE SKILLS
{skills_content}

---

## GLOBAL RULES
- ALWAYS return valid JSON when required
- NEVER add explanations unless explicitly requested
- FOLLOW output formats strictly
"""

    return system_prompt.strip()