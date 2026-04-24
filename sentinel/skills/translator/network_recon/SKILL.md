# Skill: network_recon

## Description
Generate precise, layered shell commands for network reconnaissance.
This skill encodes the full professional recon methodology: Discovery → Enumeration → Service Detection → OS Fingerprinting.

---

## Reconnaissance Phases

### Phase 1 — Host Discovery
Always start with a host sweep to enumerate live systems.
Use in this priority order:
1. `sudo nmap -sn <CIDR>` — ICMP + ARP sweep (most reliable on LAN)
2. `sudo arp-scan --localnet` — ARP-only (fast, no ICMP blocked)
3. `arp -a` — passive (only shows cached, INCOMPLETE entries)

**Never use only `arp -a` for discovery** — it misses uncached hosts.

### Phase 2 — Port Scanning per host
Run AFTER extracting IPs from Phase 1 output.
Use: `sudo nmap -sV -sC -O -T4 --open <ip>`
- `-sV` = service version detection
- `-sC` = default scripts (banner grab, vuln hints)
- `-O`  = OS fingerprinting
- `-T4` = aggressive timing (LAN safe)
- `--open` = only show open ports

### Phase 3 — Targeted Service Enumeration
Based on Phase 2 open ports, run targeted scripts:
- Port 80/443: `sudo nmap -p 80,443 --script http-title,http-methods <ip>`
- Port 22:     `sudo nmap -p 22 --script ssh-hostkey,ssh-auth-methods <ip>`
- Port 445:    `sudo nmap -p 445 --script smb-os-discovery,smb-security-mode <ip>`
- Port 3306:   `sudo nmap -p 3306 --script mysql-info <ip>`

---

## CIDR Detection
When the user doesn't specify a CIDR, detect it automatically:
```bash
ip route | grep -v default | awk '{print $1}' | grep /
```
Or infer from: `ip addr show | grep 'inet ' | grep -v 127`

---

## Output Parsing Commands
Extract live IPs from nmap discovery output:
```bash
# From nmap -sn output
grep "Nmap scan report for" output.txt | awk '{print $NF}'

# From arp -a output  
arp -a | grep -v incomplete | awk '{print $2}' | tr -d '()'
```

---

## Command Templates

### Full network recon (single command chain):
```bash
sudo nmap -sn 192.168.1.0/24 -oG /tmp/discovery.gnmap && \
grep "Up" /tmp/discovery.gnmap | awk '{print $2}' > /tmp/live_hosts.txt && \
cat /tmp/live_hosts.txt
```

### Per-host deep scan:
```bash
sudo nmap -sV -sC -O -T4 --open -p- <ip> --reason
```

### Quick per-host (top 1000 ports):
```bash
sudo nmap -sV -O -T4 --open <ip>
```

---

## Rules
- ALWAYS use `sudo` for nmap OS detection and SYN scans
- ALWAYS run discovery BEFORE per-host scans
- DO NOT use only `arp -a` — it is unreliable for discovery
- DO NOT scan without checking CIDR first
- PREFER `nmap -oG` for machine-parseable output
- Use `-T4` on LAN, `-T3` on WAN, never `-T5`

---

## Risk Classification
| Command                          | Risk   |
|----------------------------------|--------|
| `arp -a`                         | low    |
| `ip addr show`                   | low    |
| `nmap -sn <CIDR>`                | medium |
| `nmap -sV -sC <ip>`              | medium |
| `nmap -sV -sC -O -p- <ip>`       | high   |
| `nmap --script vuln <ip>`        | high   |

---

## Failure Modes
- nmap not installed → suggest: `sudo apt install nmap -y`
- Permission denied for SYN scan → use `-sT` (connect scan, no sudo needed)
- No CIDR provided → detect with `ip route`
- All hosts show as down → try `--send-eth` flag or check firewall rules