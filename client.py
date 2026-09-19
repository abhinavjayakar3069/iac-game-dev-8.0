"""Terminal Mafia - human player client.

Usage: python client.py <host> <port>
"""
import os
import socket
import sys
import threading

from mafia import protocol
from mafia.colors import colorize


def handle_message(msg):
    mtype = msg.get("type")

    if mtype == "text":
        print("\n" + colorize(msg.get("text", ""), msg.get("color")))

    elif mtype == "chat":
        print(f"\n{colorize(msg.get('from', '?') + ':', 'bold')} {msg.get('text', '')}")

    elif mtype == "lobby":
        names = msg.get("players", [])
        print("\n" + colorize(
            f"Players in lobby ({len(names)}/{msg.get('min_players')} min): " + ", ".join(names), "cyan"))

    elif mtype == "role":
        print("\n" + colorize(f"=== Your role: {msg.get('role')} ===", "bold"))
        print(colorize(msg.get("description", ""), "magenta"))
        teammates = msg.get("teammates") or []
        if teammates:
            print(colorize("Your fellow Mafia: " + ", ".join(teammates), "red"))

    elif mtype == "prompt":
        print()
        print(colorize(msg.get("text", "Choose:"), "yellow"))
        for opt in msg.get("options", []):
            print(f"  {opt['num']}. {opt['name']}")
        print(colorize(f"(You have {msg.get('time_limit')}s. Type a number, a name, or 'skip'.)", "dim"))
        print("> ", end="", flush=True)

    elif mtype == "investigate_result":
        verdict = "IS Mafia" if msg.get("is_mafia") else "is NOT Mafia"
        print("\n" + colorize(f"Investigation result: {msg.get('target')} {verdict}", "cyan"))

    elif mtype == "game_over":
        print("\n" + colorize("=== GAME OVER ===", "bold"))
        print(colorize(f"Winner: {msg.get('winner')}", "green"))
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

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    print(colorize(f"Connected to Terminal Mafia server at {host}:{port}", "green"))

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
