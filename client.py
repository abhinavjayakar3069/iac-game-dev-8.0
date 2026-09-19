"""Terminal Mafia: Ghost Protocol - human player client.

A hacker/heist presentation skin over the standard Mafia mechanic: the
wire protocol and roles are unchanged, only how they're displayed here.

Usage: python client.py <host> <port>
"""
import os
import socket
import sys
import threading
import time

from mafia import protocol
from mafia.colors import colorize

ASCII_BANNER = r"""
   ___  __  __  ____  ___  ______  ____   ___  ______ ____   ____   ___   __
  / _ |/ / / / / __ \/ _ \/_  __/ / __ \ / _ \/_  __// __ \ / __/  / _ | / /
 / __ / /_/ / / /_/ / , _/ / /   / /_/ // , _/ / /  / /_/ /_\ \   / __ |/ /_
/_/ |_\____/  \____/_/|_| /_/    \____//_/|_| /_/   \____//___/  /_/ |_/___/
                       G H O S T   P R O T O C O L
"""

PHASE_BANNERS = {
    "night": ("INFILTRATION", "blue"),
    "day_discuss": ("COUNTERMEASURES SWEEP", "yellow"),
    "vote": ("PURGE PROTOCOL", "red"),
    "game_over": ("LOCKDOWN COMPLETE", "green"),
}

ROLE_DISPLAY = {
    "Mafia": ("INFILTRATOR", "Embedded operative - sabotage the crew from within."),
    "Doctor": ("FIREWALL SPECIALIST", "Shield one system from tonight's breach."),
    "Detective": ("WHITE-HAT", "Scan one target per cycle for intrusions."),
    "Villager": ("CREW MEMBER", "Trusted crew - root out the infiltrator before it's too late."),
}

PROMPT_LABELS = {
    "kill": "SELECT BREACH TARGET",
    "save": "SELECT SYSTEM TO FIREWALL",
    "investigate": "SELECT TARGET TO SCAN",
    "vote": "CAST YOUR VOTE - WHO IS THE INFILTRATOR?",
}


def typing_effect(text, color=None, delay=0.012):
    for ch in text:
        sys.stdout.write(colorize(ch, color))
        sys.stdout.flush()
        time.sleep(delay)
    print()


def phase_banner(phase, round_no):
    label, color = PHASE_BANNERS.get(phase, (phase.upper(), None))
    suffix = f" - CYCLE {round_no}" if round_no else ""
    line = "=" * 60
    print("\n" + colorize(line, color))
    print(colorize(f">> {label}{suffix} <<".center(60), "bold"))
    print(colorize(line, color))


def handle_message(msg):
    mtype = msg.get("type")

    if mtype == "phase":
        phase_banner(msg.get("phase"), msg.get("round"))

    elif mtype == "text":
        print("\n" + colorize(msg.get("text", ""), msg.get("color")))

    elif mtype == "chat":
        print(f"\n{colorize(msg.get('from', '?') + ':', 'bold')} {msg.get('text', '')}")

    elif mtype == "lobby":
        names = msg.get("players", [])
        print("\n" + colorize(
            f"Operatives connected ({len(names)}/{msg.get('min_players')} min): " + ", ".join(names), "cyan"))

    elif mtype == "role":
        role = msg.get("role")
        codename, flavor = ROLE_DISPLAY.get(role, (role, ""))
        print()
        typing_effect("> DECRYPTING CLASSIFIED DOSSIER...", "green")
        print(colorize(f"=== YOUR COVER IDENTITY: {role.upper()} ({codename}) ===", "bold"))
        print(colorize(flavor, "magenta"))
        teammates = msg.get("teammates") or []
        if teammates:
            print(colorize("Fellow infiltrators in the network: " + ", ".join(teammates), "red"))

    elif mtype == "prompt":
        label = PROMPT_LABELS.get(msg.get("kind"), msg.get("text", "Choose:"))
        print()
        print(colorize(f"> {label}", "yellow"))
        for opt in msg.get("options", []):
            print(f"  {opt['num']}. {opt['name']}")
        print(colorize(f"(You have {msg.get('time_limit')}s. Type a number, a name, or 'skip'.)", "dim"))
        print("> ", end="", flush=True)

    elif mtype == "investigate_result":
        verdict = "FLAGGED AS INFILTRATOR" if msg.get("is_mafia") else "CLEAN - no intrusion detected"
        print("\n" + colorize(f"> SCAN COMPLETE: {msg.get('target')} - {verdict}", "cyan"))

    elif mtype == "game_over":
        winner = msg.get("winner")
        winner_label = "THE INFILTRATORS" if winner == "mafia" else "THE CREW"
        print("\n" + colorize(f">> {winner_label} WIN <<", "bold"))
        print(colorize("Identities declassified:", "cyan"))
        for name, role in msg.get("roles", {}).items():
            print(f"  {name}: {role}")


def receiver(sock):
    reader = protocol.LineReader()
    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            for msg in reader.feed(data):
                handle_message(msg)
    except OSError:
        pass
    print("\n" + colorize("Disconnected from server. Press Enter to exit.", "yellow"))
    os._exit(0)


def main():
    if len(sys.argv) < 3:
        print("Usage: python client.py <host> <port>")
        sys.exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])

    print(colorize(ASCII_BANNER, "cyan"))
    typing_effect(f"> ESTABLISHING SECURE UPLINK TO {host}:{port}...", "dim")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    typing_effect("> UPLINK ESTABLISHED.", "green")

    threading.Thread(target=receiver, args=(sock,), daemon=True).start()

    try:
        while True:
            line = input()
            sock.sendall(protocol.encode({"type": "input", "text": line}))
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()
