import json
import time
import uuid
import os

TRACE_FILE = "logs/traces.json"


class Tracer:

    def __init__(self):
        self.trace_id = str(uuid.uuid4())
        self.steps = []

    def log(self, agent, action, data=None):
        self.steps.append({
            "timestamp": time.time(),
            "agent": agent,
            "action": action,
            "data": data
        })

    def save(self):
        os.makedirs("logs", exist_ok=True)

        trace = {
            "trace_id": self.trace_id,
            "steps": self.steps
        }

        with open(TRACE_FILE, "a") as f:
            f.write(json.dumps(trace) + "\n")

        return trace