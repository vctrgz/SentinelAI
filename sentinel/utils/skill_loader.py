import os
from utils.prompt_loader import load_file


SKILLS_PATH = "skills"


def load_skills(skill_names: list) -> str:
    """
    Carga el contenido de los skills necesarios
    """

    skills_content = []

    for skill in skill_names:
        path = os.path.join(SKILLS_PATH, f"{skill}.md")

        if os.path.exists(path):
            content = load_file(path)
            skills_content.append(f"# Skill: {skill}\n{content}")
        else:
            skills_content.append(f"# Skill: {skill}\n(Not found)")

    return "\n\n".join(skills_content)