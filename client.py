"""Terminal Mafia: Ghost Protocol - human player client.

A hacker/heist presentation skin over the standard Mafia mechanic: the
wire protocol and roles are unchanged, only how they're displayed here.

Usage: python client.py <host> <port>
"""
import os
import socket
import sys
import threading

from mafia import protocol
from mafia.colors import colorize

# Legacy Windows consoles (default cmd.exe codepages) can't encode every
# Unicode character; without this, a single odd character in any chat/
# broadcast text would crash the client mid-game with UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

ASCII_BANNER = r"""
@@@@@ @@@ @   @ @@@@     @@@@@ @   @ @@@@@    @@@@@ @   @  @@@  @@@ @   @ @@@@@ @@@@@ @@@@  
@      @  @@  @ @   @      @   @   @ @        @     @@  @ @      @  @@  @ @     @     @   @ 
@@@@   @  @ @ @ @   @      @   @@@@@ @@@@     @@@@  @ @ @ @  @@  @  @ @ @ @@@@  @@@@  @@@@  
@      @  @  @@ @   @      @   @   @ @        @     @  @@ @   @  @  @  @@ @     @     @  @  
@     @@@ @   @ @@@@       @   @   @ @@@@@    @@@@@ @   @  @@@  @@@ @   @ @@@@@ @@@@@ @   @ 
"""

PHASE_BANNERS = {
    "night": ("INFILTRATION", "blue"),
    "day_discuss": ("COUNTERMEASURES SWEEP", "yellow"),
    "vote": ("PURGE PROTOCOL", "red"),
    "game_over": ("LOCKDOWN COMPLETE", "green"),
}

ROLE_DISPLAY = {
    "Engineer": ("INFILTRATOR", "Each night, convert one player into a fellow Engineer. Win when Engineers equal or outnumber everyone else."),
    "Doctor": ("FIREWALL SPECIALIST", "Each night, shield one player from being converted."),
    "Police": ("ENFORCER", "Each night, send one player to jail - they're eliminated, no exceptions."),
    "Professor": ("ANALYST", "Each night, deduct a point from another player and add it to your own score."),
}

PROMPT_LABELS = {
    "infect": "SELECT TARGET TO CONVERT",
    "save": "SELECT PLAYER TO PROTECT",
    "detain": "SELECT PLAYER TO SEND TO JAIL",
    "steal": "SELECT PLAYER TO DEDUCT A POINT FROM",
    "vote": "CAST YOUR VOTE - WHO IS AN ENGINEER?",
}


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
        print(colorize(f"=== YOUR ROLE: {role.upper()} ===", "bold"))
        if codename:
            print(colorize(f"(codename: {codename})", "dim"))
        print(colorize(flavor, "magenta"))
        teammates = msg.get("teammates") or []
        if teammates:
            print(colorize("Your fellow Engineers: " + ", ".join(teammates), "red"))

    elif mtype == "prompt":
        label = PROMPT_LABELS.get(msg.get("kind"), msg.get("text", "Choose:"))
        print()
        print(colorize(f"> {label}", "yellow"))
        for opt in msg.get("options", []):
            print(f"  {opt['num']}. {opt['name']}")
        print(colorize(f"(You have {msg.get('time_limit')}s. Type a number, a name, or 'skip'.)", "dim"))
        print("> ", end="", flush=True)

    elif mtype == "game_over":
        winner = msg.get("winner")
        winner_label = "THE INFILTRATORS" if winner == "mafia" else "THE CREW"
        print("\n" + colorize(f">> {winner_label} WIN <<", "bold"))
        print(colorize("Identities declassified:", "cyan"))
        scores = msg.get("scores", {})
        for name, role in msg.get("roles", {}).items():
            print(f"  {name}: {role} (score: {scores.get(name, 0)})")


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
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    print(colorize(f"Connected to {host}:{port}.", "green"))

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
