"""Terminal Mafia - AI bot client, for filling seats during testing/demos.

Usage: python bot_client.py <host> <port> [name]
(or just python bot_client.py / double-click the .exe - it will try to
find the server automatically, then prompt if it can't)
"""
import random
import socket
import sys
import time

from mafia import discovery, protocol

CHAT_LINES = [
    "I'm not sure who to trust yet.",
    "Someone's acting suspicious today.",
    "Let's think this through carefully.",
    "I have a feeling about someone...",
    "We need to work together to find the Grad Student.",
    "That vote yesterday felt off to me.",
    "I'll stay quiet and observe for now.",
]


def main():
    if len(sys.argv) >= 3:
        host = sys.argv[1]
        port = int(sys.argv[2])
        name = sys.argv[3] if len(sys.argv) > 3 else f"Bot{random.randint(100, 999)}"
    else:
        # No <host> <port> passed on the command line - this happens when
        # the .exe is launched by double-clicking it rather than from a
        # terminal (or from server.py's --bots, which always passes args
        # and so never hits this branch).
        print("Looking for a server on this network...")
        found = discovery.find_server()
        if found:
            host, port = found
            print(f"Found server at {host}:{port}.")
        else:
            print("No server found automatically - enter it manually.")
            host = input("Server IP address (blank for 127.0.0.1): ").strip() or "127.0.0.1"
            while True:
                port_text = input("Port (blank for 5050): ").strip() or "5050"
                try:
                    port = int(port_text)
                    break
                except ValueError:
                    print("Enter a number for the port.")
        name = f"Bot{random.randint(100, 999)}"

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
    except OSError as e:
        print(f"Could not connect to {host}:{port} ({e}).")
        input("Press Enter to exit.")
        return
    reader = protocol.LineReader()
    state = {"name_sent": False, "known_names": set()}

    def send(obj):
        try:
            sock.sendall(protocol.encode(obj))
        except OSError:
            pass

    def handle(msg):
        mtype = msg.get("type")

        if mtype == "lobby":
            state["known_names"].update(msg.get("players", []))
            # If a bot happens to be host (e.g. solo testing with all bots),
            # nudge the lobby along once enough players have joined. This is
            # a harmless no-op ('start' is just chat) when the bot isn't host.
            if len(msg.get("players", [])) >= msg.get("min_players", 4):
                time.sleep(random.uniform(1.5, 3.0))
                send({"type": "input", "text": "start"})

        elif mtype == "chat":
            sender = msg.get("from", "").replace("[spectator] ", "")
            if sender:
                state["known_names"].add(sender)

        elif mtype == "text":
            text = msg.get("text", "")
            if not state["name_sent"] and "name" in text.lower():
                time.sleep(random.uniform(0.2, 0.8))
                send({"type": "input", "text": name})
                state["name_sent"] = True
            elif "Discussion phase" in text:
                time.sleep(random.uniform(2.0, 6.0))
                others = [n for n in state["known_names"] if n != name]
                if others and random.random() < 0.4:
                    send({"type": "input", "text": f"accuse {random.choice(others)}"})
                else:
                    send({"type": "input", "text": random.choice(CHAT_LINES)})
            elif "last words" in text.lower() and text.startswith("You have been eliminated"):
                time.sleep(random.uniform(0.5, 2.0))
                send({"type": "input", "text": random.choice(["It wasn't me!", "You'll regret this.", "Good luck, village."])})

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
