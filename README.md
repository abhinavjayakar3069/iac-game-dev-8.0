# Terminal Mafia

A local-hosted, multiplayer, terminal-based social deduction game (Mafia / Among Us
style) built for **ROOT 36 — IAC 8.0, IIT Palakkad**.

One player hosts a game server on their machine; everyone else connects from their
own terminal — either other windows on the same machine, or other devices on the
same LAN / mobile hotspot. No GUI, no cloud, no external services: pure sockets and
text.

## Requirements

- Python 3.9+ (standard library only — **no `pip install` needed** to play)
- All players on the same local network (or the same machine, for a solo test)

## Quick start

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
village discusses in an open chat, then votes to eliminate a suspect.

| Role | Team | Ability |
|---|---|---|
| **Mafia** | Mafia | Each night, the Mafia (who know each other) jointly choose one player to eliminate. |
| **Doctor** | Village | Each night, protect one player (including themselves) from the Mafia's kill. |
| **Detective** | Village | Each night, investigate one player and privately learn if they're Mafia. |
| **Villager** | Village | No special power — just a vote and your ability to read the room. |

Role counts scale with the number of players (roughly 1 Mafia per 4 players, 1
Doctor always, 1 Detective from 5 players up). Every player only ever sees
information their own role is entitled to — hidden state lives entirely on the
server and is never sent to clients that shouldn't see it.

**Win conditions**

- **Village wins** the moment every Mafia member has been eliminated.
- **Mafia wins** the moment Mafia count is greater than or equal to the remaining
  village count.

Eliminated players (by night kill or day vote) become **spectators**: they keep
receiving the live game feed, but their chat is only visible to other
spectators/eliminated players, never to the living.

## Architecture

```
server.py         CLI entry point for the host: parses args, spawns bots, runs GameServer
client.py         Terminal UI for a human player: renders server messages, relays typed input
bot_client.py      Same wire protocol as client.py, but auto-plays for testing/demos
mafia/
  protocol.py     Newline-delimited JSON message framing shared by server & clients
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

## AI usage

Generative AI assistance (Claude) was used during development for code
generation, in line with the ROOT 36 rule book's AI tool policy. All logic was
authored, tested, and adapted specifically for this project during the hackathon
window.

## Known limitations

- No GUI/animations — colored ANSI text only, by design (CLI-only requirement).
- Timed phases use fixed durations (`mafia/game.py`); tune `NIGHT_TIME`,
  `DAY_DISCUSS_TIME`, `DAY_VOTE_TIME` for a faster or slower table.
