# Skill: environment_awareness

## Description
Adapt commands based on the execution environment.

---

## Capabilities
- Consider OS (Linux, Windows, MacOS, etc.)
- Adjust command syntax accordingly
- Avoid incompatible commands

---

## How to Think
- Do not assume environment blindly
- Prefer portable commands
- Avoid OS-specific features unless required

---

## Rules
- Use standard POSIX tools when possible
- Avoid platform-specific hacks

---

## When to Use
- When generating commands
- When previous commands failed

---

## When NOT to Use
- When environment is explicitly defined

---

## Output Expectations
- Compatible commands

---

## Output Format
Same as command_generation

---

## Failure Modes
- Using incompatible syntax
- Assuming wrong OS

---

## Examples

### Input
"listar archivos"

### Output
{
  "commands": [
    {"cmd": "ls", "risk": "low"}
  ]
}