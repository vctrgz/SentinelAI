import shutil
import shlex


class CommandValidator:

    def __init__(self):
        self.dangerous_patterns = [
            "rm -rf /",
            "mkfs",
            "dd ",
            "shutdown",
            "reboot"
        ]

    def validate(self, cmd: str) -> dict:
        """
        Valida:
        - existencia del comando
        - seguridad básica
        """

        # 🔹 seguridad básica
        for pattern in self.dangerous_patterns:
            if pattern in cmd:
                return {
                    "valid": False,
                    "reason": "dangerous_command"
                }

        # 🔹 parseo
        try:
            parts = shlex.split(cmd)
            base_cmd = parts[0]
        except Exception:
            return {
                "valid": False,
                "reason": "invalid_syntax"
            }

        # 🔹 comprobar si existe
        if shutil.which(base_cmd) is None:
            return {
                "valid": False,
                "reason": "command_not_found"
            }

        return {
            "valid": True,
            "reason": "ok"
        }