class TaskRouter:

    def __init__(self, shell_executor, tool_manager):
        self.shell_executor = shell_executor
        self.tool_manager = tool_manager

    def route(self, commands):

        routed = []

        for cmd_obj in commands:
            cmd = cmd_obj["cmd"]

            base = cmd.split()[0]

            if base in ["apt", "pip"]:
                routed.append({
                    "executor": "tool_manager",
                    "cmd": cmd
                })
            else:
                routed.append({
                    "executor": "shell",
                    "cmd": cmd
                })

        return routed

    def execute(self, commands):

        results = []

        routed = self.route(commands)

        for item in routed:

            if item["executor"] == "shell":
                results.append(self.shell_executor.execute(item["cmd"]))

            elif item["executor"] == "tool_manager":
                tool = item["cmd"].split()[-1]
                results.append(self.tool_manager.ensure_tool(tool))

        return results