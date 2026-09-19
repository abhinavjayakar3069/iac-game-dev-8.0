"""Terminal Mafia - AI bot client, for filling seats during testing/demos.

Usage: python bot_client.py <host> <port> [name]
"""
import random
import socket
import sys
import time

from mafia import protocol

CHAT_LINES = [
    "I'm not sure who to trust yet.",
    "Someone's acting suspicious today.",
    "Let's think this through carefully.",
    "I have a feeling about someone...",
    "We need to work together to find the Mafia.",
    "That vote yesterday felt off to me.",
    "I'll stay quiet and observe for now.",
]


def main():
    if len(sys.argv) < 3:
        print("Usage: python bot_client.py <host> <port> [name]")
        sys.exit(1)
    host = sys.argv[1]
    port = int(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else f"Bot{random.randint(100, 999)}"

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    reader = protocol.LineReader()
    state = {"name_sent": False}

    def send(obj):
        try:
            sock.sendall(protocol.encode(obj))
        except OSError:
            pass

    def handle(msg):
        mtype = msg.get("type")
        if mtype == "text":
            text = msg.get("text", "")
            if not state["name_sent"] and "name" in text.lower():
                time.sleep(random.uniform(0.2, 0.8))
                send({"type": "input", "text": name})
                state["name_sent"] = True
            elif "Discussion phase" in text:
                time.sleep(random.uniform(2.0, 6.0))
                send({"type": "input", "text": random.choice(CHAT_LINES)})
        elif mtype == "lobby":
            # If a bot happens to be host (e.g. solo testing with all bots),
            # nudge the lobby along once enough players have joined. This is
            # a harmless no-op ('start' is just chat) when the bot isn't host.
            if len(msg.get("players", [])) >= msg.get("min_players", 4):
                time.sleep(random.uniform(1.5, 3.0))
                send({"type": "input", "text": "start"})
        elif mtype == "prompt":
            options = msg.get("options", [])
            time.sleep(random.uniform(1.0, 3.0))
            if options and random.random() > 0.1:
                choice = random.choice(options)
                send({"type": "input", "text": str(choice["num"])})
            else:
                send({"type": "input", "text": "skip"})

    try:
        while True:
            data = sock.recv(4096)
            if not data:
                break
            for msg in reader.feed(data):
                handle(msg)
    except OSError:
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()
