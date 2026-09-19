# Terminal Mafia — Ghost Protocol

A local-hosted, multiplayer, terminal-based social deduction game (Mafia / Among Us
style) built for **ROOT 36 — IAC 8.0, IIT Palakkad**.

"Ghost Protocol" is a hacker/heist presentation skin on top of the standard Mafia
mechanic: an infiltrator is hiding among a crew of operatives. The wire protocol
and game rules are untouched — only the terminal client's banners, role flavor
text, and phase names are themed.

One player hosts a game server on their machine; everyone else connects from their
own terminal — either other windows on the same machine, or other devices on the
same LAN / mobile hotspot. No GUI, no cloud, no external services: pure sockets and
text.

## Requirements

- Python 3.9+ (standard library only — **no `pip install` needed** to play), **or**
  the prebuilt Windows executables in [`dist/`](dist/) if you don't have Python
- All players on the same local network (or the same machine, for a solo test)

## Quick start (prebuilt executables)

No Python required. From `dist/`:

```bash
dist\terminal-mafia-server.exe --port 5050
```

Everyone else:

```bash
dist\terminal-mafia-client.exe <host-ip> 5050
```

All three also work by double-clicking the `.exe` directly (no terminal
needed) - `terminal-mafia-server.exe` starts on the default port 5050, and
`terminal-mafia-client.exe` / `terminal-mafia-bot.exe` will try to find the
server automatically on the local network/hotspot, falling back to asking
for the host IP and port if nothing answers (some phone hotspots block
this kind of discovery).

(`terminal-mafia-bot.exe` is the AI bot, used automatically by `--bots N`.)
Rebuild them yourself anytime with `pip install pyinstaller` and
`python -m PyInstaller --onefile server.py` (same for `client.py` /
`bot_client.py`) — they're just packaged copies of the scripts below.

## Quick start (from source)

**1. Host starts the server** (pick any free port, e.g. 5050):

```bash
python server.py --port 5050
```

The server prints its own bind address. Find the host machine's LAN IP with
`ipconfig` (Windows) / `ifconfig` or `ip addr` (Mac/Linux) — look for something like
`192.168.x.x`.

**2. Everyone else connects** from their own terminal:

```bash
python client.py <host-ip> 5050
```

On the same machine, just open more terminal windows and connect to `127.0.0.1`
instead of a LAN IP.

**3. Enter a name when prompted.** The first player to join is the **host** and can
type `start` once at least 4 players (configurable) have joined.

**4. Play.** Prompts tell you exactly what to do each phase — type a number, a
player's name, or `skip`.

### Solo testing without other humans

The server can auto-spawn AI bot players so you can test or demo the full game
loop alone:

```bash
python server.py --port 5050 --bots 4
```

### Options

```
python server.py [--port 5050] [--host 0.0.0.0] [--min-players 4] [--bots 0]
```

## How to play

Each night, players with special roles secretly submit an action. Each day, the
crew discusses in an open chat, then votes to eliminate a suspect.

| Role | Team | Ability |
|---|---|---|
| **Engineer** | Engineers | Each night, the Engineers (who know each other) jointly choose one player to try to convert. The target gets a real choice — accept and join the Engineers, or refuse and stay as they are. |
| **Doctor** | Everyone else | Each night, protect one player (including themselves) from being converted. |
| **Police** | Everyone else | Each night, send one player to jail — this permanently eliminates them, with no way to block it. |
| **Professor** | Everyone else | Each night, deduct a point from another player and add it to your own score. No effect on who's alive. |

Role counts scale with the number of players (roughly 1 Engineer per 4 players, 1
Doctor always, 1 Police from 5 players up, everyone else is a Professor). Every
player only ever sees information their own role is entitled to — hidden state
lives entirely on the server and is never sent to clients that shouldn't see it.

**Conversion is a choice, not a coin flip you don't get a say in.** Accepting an
Engineer's offer gives you +2 points and puts you on their team; refusing costs
you 1 point but keeps your original role. Final scores are shown on the
end-of-game screen for everyone.

**Discussion isn't just a timer.** During the day, type `accuse <name>` to publicly
flag a suspect — it updates a live suspicion tally broadcast to the whole table,
on top of free-form chat.

**Last words.** A player voted out during the day gets a short window to speak
before their identity is revealed to everyone.

**Win conditions**

- **Everyone else wins** the moment every Engineer has been eliminated.
- **The Engineers win** the moment their count is greater than or equal to
  everyone else remaining.

Eliminated players (by jail or day vote) become **spectators**: they keep
receiving the live game feed, but their chat is only visible to other
spectators/eliminated players, never to the living.

**Reconnecting.** If you drop mid-game, reconnect with `python client.py <host> <port>`
and enter the *exact same name* you had before — you'll resume your seat, role,
and alive/dead status instead of being locked out.

## Architecture

```
server.py         CLI entry point for the host: parses args, spawns bots, runs GameServer
client.py         Terminal UI for a human player: renders server messages, relays typed input
bot_client.py      Same wire protocol as client.py, but auto-plays for testing/demos
mafia/
  protocol.py     Newline-delimited JSON message framing shared by server & clients
  discovery.py    UDP broadcast/reply so the client can auto-find a server on the LAN
  roles.py        Pure role definitions + role-count distribution (no I/O, unit-testable)
  game.py         GameServer: connection handling + the night/day phase state machine
  colors.py       Dependency-free ANSI color helpers for the terminal UI
match_history/    One human-readable log file per completed match
```

**Networking model:** the server is authoritative. It accepts TCP connections and
spawns one lightweight reader thread per client; those threads only ever push
incoming messages onto a single thread-safe queue. All game-state mutation
(role assignment, phase transitions, vote tallying, win checks) happens on one
thread, so there's no locking to get wrong around the actual game logic. Every
role-specific prompt, private investigation result, and chat visibility rule is
resolved server-side — a client only ever receives what its role is allowed to
know.

**Resilience:** a disconnect at any point (lobby, night action, discussion, vote)
is caught and handled gracefully — the player is marked disconnected, the rest of
the table is notified, the win condition is re-checked, and if the disconnecting
player was the host, host status is transferred automatically. Invalid input
(bad menu numbers, unknown names) is rejected with a re-prompt instead of
crashing the server or blocking other players.

## Tests

`mafia/roles.py` is pure logic (no sockets/threads), so it's unit-tested
directly. There's also a live integration suite that spins up a real
`GameServer` on a loopback socket and throws malformed JSON, oversized
payloads, wrong-typed fields, unknown message types, and abrupt disconnects
at it — confirming a broken/hostile client can never take the game down for
everyone else.

```bash
python -m unittest discover tests -v
```

## AI usage

Generative AI assistance (Claude) was used during development for code
generation, in line with the ROOT 36 rule book's AI tool policy. All logic was
authored, tested, and adapted specifically for this project during the hackathon
window.

## Known limitations

- No GUI/animations — colored ANSI text only, by design (CLI-only requirement).
- Timed phases use fixed durations (`mafia/game.py`); tune `NIGHT_TIME`,
  `DAY_DISCUSS_TIME`, `DAY_VOTE_TIME` for a faster or slower table.
