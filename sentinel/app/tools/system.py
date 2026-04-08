import subprocess

def execute_command(command: str):
    try:
        # Separar comando base
        base_cmd = command.split()[0]

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=5
        )

        output = result.stdout or result.stderr

        # Limitar output
        return output[:2000]

    except Exception as e:
        return f"Error ejecutando comando: {str(e)}"