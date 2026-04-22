import os
import glob
from typing import Optional
from utils.file_utils import load_file  # Fix #3: era 'from utils.prompt_loader import load_file'


SKILLS_PATH = "skills"


def find_skill_file(skill_name: str) -> Optional[str]:
    """
    Hace búsqueda recursiva para encontrar el SKILL.md
    correspondiente al nombre de skill en cualquier subdirectorio.

    Estrategia de búsqueda (en orden de prioridad):
    1. skills/**/skill_name/SKILL.md   (estructura actual del proyecto)
    2. skills/**/skill_name.md         (estructura plana)
    3. skills/skill_name/SKILL.md      (directo)
    """
    # 1. Búsqueda recursiva: el directorio se llama igual que la skill
    pattern = os.path.join(SKILLS_PATH, "**", skill_name, "SKILL.md")
    matches = glob.glob(pattern, recursive=True)
    if matches:
        return matches[0]

    # 2. Búsqueda recursiva: archivo markdown con ese nombre
    pattern2 = os.path.join(SKILLS_PATH, "**", f"{skill_name}.md")
    matches2 = glob.glob(pattern2, recursive=True)
    if matches2:
        return matches2[0]

    # 3. Ruta directa (por si acaso)
    direct = os.path.join(SKILLS_PATH, skill_name, "SKILL.md")
    if os.path.exists(direct):
        return direct

    return None


def load_skills(skill_names: list) -> str:
    """
    Carga y concatena el contenido de todos los skills solicitados.
    Ahora con rutas correctas gracias a find_skill_file().
    """
    if not skill_names:
        return "(No skills defined)"

    skills_content = []

    for skill in skill_names:
        path = find_skill_file(skill)
        if path:
            content = load_file(path)
            skills_content.append(f"# Skill: {skill}\n{content}")
        else:
            skills_content.append(f"# Skill: {skill}\n(Skill file not found)")

    return "\n\n".join(skills_content)