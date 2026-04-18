# 🔴 Comandos peligrosos (bloqueo o confirmación obligatoria)
CRITICAL_COMMAND_PATTERNS = [
    "rm -rf",
    "shutdown",
    "reboot",
    "mkfs",
    "dd ",
    ":(){ :|:& };:",  # fork bomb
    "chmod 777",
    "chown",
    "iptables",
    "ufw disable"
]

# 🟡 Comandos que requieren confirmación
SENSITIVE_COMMANDS = [
    "apt install",
    "pip install",
    "npm install",
    "git clone",
    "docker",
    "systemctl"
]

# 🟢 Comandos seguros (whitelist inicial)
SAFE_COMMANDS = [
    "ls",
    "pwd",
    "echo",
    "cat",
    "whoami",
    "date"
]

# 📊 Estados de ejecución
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_PARTIAL = "partial"
STATUS_FATAL = "fatal"
STATUS_RETRY = "retry"