"""Core game server: connection handling and the night/day game loop.

All game-state mutation happens on a single thread (the thread that calls
GameServer.run). Per-connection reader threads only ever push messages onto
a thread-safe queue; they never touch shared state directly. This keeps the
game logic free of locking concerns while still supporting real concurrent
socket I/O across many players.
"""
import os
import queue
import random
import socket
import subprocess
import sys
import threading
import time
from collections import Counter

from mafia import protocol, roles


def _bot_command():
    """Build the subprocess command for a bot client, working both when
    running from source and when frozen into a standalone .exe (where
    sys.executable is this program itself, not a Python interpreter)."""
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        for candidate in ("terminal-mafia-bot.exe", "bot_client.exe"):
            path = os.path.join(exe_dir, candidate)
            if os.path.isfile(path):
                return [path]
        return None
    server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [sys.executable, os.path.join(server_dir, "bot_client.py")]


class Player:
    def __init__(self, pid, conn, addr):
        self.id = pid
        self.conn = conn
        self.addr = addr
        self.name = None
        self.role = None
        self.alive = True
        self.connected = True
        self.is_host = False
        self.spectator = False
        self.score = 0
        # Input routing state: what kind of reply we're expecting next.
        self.pending = None          # None | "name" | "action"
        self.pending_kind = None     # "kill" | "save" | "investigate" | "vote"
        self.pending_options = []    # list[Player] the reply must resolve to


class GameServer:
    NIGHT_TIME = 35
    DAY_DISCUSS_TIME = 45
    DAY_VOTE_TIME = 30
    CONVERT_ACCEPT_BONUS = 2
    CONVERT_REFUSE_PENALTY = 1
    MAX_BOTS_PER_REQUEST = 20

    def __init__(self, host="0.0.0.0", port=5050, min_players=4):
        self.host = host
        self.port = port
        self.min_players = min_players

        self.players = {}
        self.inbound = queue.Queue()
        self._next_id = 1

        self.log = []
        self.round = 0
        self.game_started = False
        self.host_id = None
        self._no_elim_streak = 0
        self._srv_sock = None

    # ------------------------------------------------------------------ #
    # Networking plumbing
    # ------------------------------------------------------------------ #
    def run(self):
        self._srv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv_sock.bind((self.host, self.port))
        self._srv_sock.listen()
        threading.Thread(target=self._accept_loop, daemon=True).start()

        try:
            self.lobby_phase()
            self.assign_roles()
            while True:
                self.night_phase()
                if self.check_win():
                    break
                self.day_phase()
                if self.check_win():
                    break
        finally:
            time.sleep(2)
            for p in list(self.players.values()):
                try:
                    p.conn.close()
                except OSError:
                    pass
            try:
                self._srv_sock.close()
            except OSError:
                pass

    def spawn_bots(self, n):
        """Launch n bot_client processes that connect to this server on
        localhost. Returns None on success, or an error string. Runs the
        actual spawning on a background thread so the caller (the game
        loop) never blocks on subprocess startup."""
        bot_cmd = _bot_command()
        if bot_cmd is None:
            return "no bot_client.py/terminal-mafia-bot.exe found next to this program."

        def _spawn():
            for _ in range(n):
                subprocess.Popen(bot_cmd + ["127.0.0.1", str(self.port)])
                time.sleep(0.2)
        threading.Thread(target=_spawn, daemon=True).start()
        return None

    def _accept_loop(self):
        # This runs on its own thread, so it must never touch self.players
        # directly - the main game-loop thread is the sole owner of that
        # dict (see module docstring). The new Player is handed off through
        # the inbound queue and only inserted once the main thread processes
        # the __connected__ event, in _handle_common.
        while True:
            try:
                conn, addr = self._srv_sock.accept()
            except OSError:
                return
            pid = self._next_id
            self._next_id += 1
            p = Player(pid, conn, addr)
            threading.Thread(target=self._client_reader, args=(p,), daemon=True).start()
            self.inbound.put((pid, {"type": "__connected__", "player": p}))

    def _client_reader(self, p):
        reader = protocol.LineReader()
        try:
            while True:
                data = p.conn.recv(4096)
                if not data:
                    break
                for msg in reader.feed(data):
                    self.inbound.put((p.id, msg))
        except OSError:
            pass
        finally:
            self.inbound.put((p.id, {"type": "__disconnect__"}))

    def send_to(self, p, obj):
        try:
            p.conn.sendall(protocol.encode(obj))
        except OSError:
            p.connected = False

    def send_text(self, p, text, color=None):
        self.send_to(p, {"type": "text", "text": text, "color": color})

    def broadcast_text(self, text, color=None, exclude=None):
        for p in self.players.values():
            if p.connected and p.id != exclude:
                self.send_text(p, text, color)

    def broadcast_phase(self, phase, round_no=None):
        """Pure UI signal: lets clients render a themed banner for this
        phase. Carries no game logic of its own - safe to ignore."""
        for p in self.players.values():
            if p.connected:
                self.send_to(p, {"type": "phase", "phase": phase, "round": round_no})

    def _log(self, text):
        self.log.append(f"[{time.strftime('%H:%M:%S')}] {text}")
        print(f"[server] {text}")

    # ------------------------------------------------------------------ #
    # Shared inbound-message handling
    # ------------------------------------------------------------------ #
    def _handle_common(self, pid, msg):
        """Handle connect/disconnect/name-entry. Returns True if the
        message was fully handled and needs no further action from the
        caller."""
        mtype = msg.get("type")

        if mtype == "__connected__":
            p = msg.get("player")
            if p is None:
                return True
            self.players[p.id] = p
            p.pending = "name"
            if self.game_started:
                p.spectator = True
                self.send_text(p, "The game is already in progress. Enter a name to join as a spectator:", "yellow")
            else:
                self.send_text(p, "Welcome to Terminal Mafia! Enter your name:", "cyan")
            return True

        if mtype == "__disconnect__":
            p = self.players.get(pid)
            if p:
                was_named = p.name is not None
                p.connected = False
                if p.alive:
                    p.alive = False
                if was_named:
                    self.broadcast_text(f"{p.name} has disconnected.", "yellow", exclude=pid)
                    self._log(f"{p.name} disconnected.")
                    if not self.game_started:
                        self._broadcast_lobby()
                if p.is_host:
                    p.is_host = False
                    self._reassign_host()
            return True

        if mtype != "input":
            return True

        p = self.players.get(pid)
        if p is None or not p.connected:
            return True

        text = str(msg.get("text", "")).strip()

        if p.pending == "name":
            if not text:
                self.send_text(p, "Name cannot be empty. Enter your name:", "red")
                return True
            text = text[:20]

            # Reconnection: someone who was mid-game and dropped can rejoin
            # under the same name and resume their seat (role, alive state).
            reconnect_target = next(
                (pl for pl in self.players.values()
                 if pl.id != pid and not pl.connected and pl.role is not None
                 and pl.name and pl.name.lower() == text.lower()),
                None,
            )
            if reconnect_target:
                old_id = reconnect_target.id
                p.name = reconnect_target.name
                p.role = reconnect_target.role
                p.alive = reconnect_target.alive
                p.spectator = False
                p.pending = None
                del self.players[old_id]
                self.send_text(p, f"Welcome back, {p.name}! You reconnected as {p.role}.", "green")
                self.send_text(p, roles.DESCRIPTIONS[p.role], "magenta")
                if not p.alive:
                    self.send_text(p, "You were eliminated before you dropped - you're watching as a spectator.", "yellow")
                self.broadcast_text(f"{p.name} has reconnected.", "green", exclude=pid)
                self._log(f"{p.name} reconnected.")
                return True

            if any(pl.name == text for pl in self.players.values() if pl.id != pid and pl.name):
                self.send_text(p, "That name is taken. Enter a different name:", "red")
                return True
            p.name = text
            p.pending = None
            self._log(f"{p.name} joined." + (" (spectator)" if p.spectator else ""))
            if p.spectator:
                self.send_text(p, f"You are watching as a spectator, {p.name}. Your chat is only visible to other spectators/eliminated players.", "yellow")
            else:
                if self.host_id is None:
                    self.host_id = pid
                    p.is_host = True
                if not self.game_started:
                    self._broadcast_lobby()
                    if p.is_host:
                        self.send_text(p, f"You are the host. Type 'start' once at least {self.min_players} players have joined, or 'bots <N>' to fill the lobby with AI players.", "cyan")
            return True

        return False  # caller resolves: pending action, or free chat

    def _reassign_host(self):
        for p in self.players.values():
            if p.connected and p.name and not p.spectator:
                p.is_host = True
                self.host_id = p.id
                self.send_text(p, "You are now the host. Type 'start' when ready, or 'bots <N>' to fill the lobby with AI players.", "cyan")
                return
        self.host_id = None

    def _broadcast_lobby(self):
        names = [p.name for p in self.players.values() if p.connected and p.name and not p.spectator]
        for p in self.players.values():
            if p.connected and p.name and not p.spectator:
                self.send_to(p, {"type": "lobby", "players": names, "min_players": self.min_players})

    def _broadcast_chat(self, p, text):
        if not text:
            return
        is_ghost = p.spectator or not p.alive
        label = f"[spectator] {p.name}" if is_ghost else p.name
        for other in self.players.values():
            if not other.connected or not other.name:
                continue
            other_is_ghost = other.spectator or not other.alive
            if is_ghost and not other_is_ghost:
                continue  # the dead/spectators can't be heard by the living
            self.send_to(other, {"type": "chat", "from": label, "text": text})
        self._log(f"chat: {label}: {text}")

    def _resolve_target(self, text, options):
        """Returns (ok, target_or_None). ok=False means invalid input."""
        t = text.strip()
        if t.lower() in ("abstain", "skip"):
            return True, None
        if t.isdigit():
            idx = int(t) - 1
            if 0 <= idx < len(options):
                return True, options[idx]
            return False, None
        for o in options:
            if o.name.lower() == t.lower():
                return True, o
        return False, None

    def _prompt(self, p, kind, options, text, time_limit):
        p.pending = "action"
        p.pending_kind = kind
        p.pending_options = options
        opts = [{"num": i + 1, "name": o.name} for i, o in enumerate(options)]
        self.send_to(p, {"type": "prompt", "kind": kind, "options": opts, "text": text, "time_limit": time_limit})

    CONVERT_OFFER_TIME = 20

    def _offer_conversion(self, target, engineers):
        """Give a would-be conversion target a real choice instead of
        silently flipping their role. Returns True if they accept.
        A disconnected target, a timeout, or any answer other than
        'accept' all count as a refusal."""
        if not target.connected:
            return False

        target.pending = "action"
        target.pending_kind = "convert_offer"
        target.pending_options = []
        self.send_to(target, {
            "type": "prompt",
            "kind": "convert_offer",
            "options": [{"num": 1, "name": "Accept"}, {"num": 2, "name": "Refuse"}],
            "text": "The Engineers want to recruit you! Accept and join them, or refuse and stay as you are:",
            "time_limit": self.CONVERT_OFFER_TIME,
        })

        answer = {"accepted": False}

        def on_message(pid, msg):
            mtype = msg.get("type")
            consumed = self._handle_common(pid, msg)
            if mtype == "__disconnect__":
                return pid == target.id
            if consumed:
                return False
            p = self.players.get(pid)
            if p is None:
                return False
            if p.id != target.id or p.pending != "action":
                text = str(msg.get("text", "")).strip()
                self._broadcast_chat(p, text)
                return False
            text = str(msg.get("text", "")).strip().lower()
            p.pending = None
            answer["accepted"] = text in ("1", "accept", "yes", "join")
            return True

        self._pump(time.time() + self.CONVERT_OFFER_TIME, on_message)
        if target.pending == "action":
            target.pending = None
        return answer["accepted"]

    def _pump(self, deadline, on_message):
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return
            try:
                pid, msg = self.inbound.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                continue
            if on_message(pid, msg):
                return

    def _plurality(self, values, tie_breaks_to_none=False):
        values = [v for v in values if v is not None]
        if not values:
            return None
        counts = Counter(values)
        top = max(counts.values())
        winners = [k for k, v in counts.items() if v == top]
        if len(winners) > 1:
            return None if tie_breaks_to_none else random.choice(winners)
        return winners[0]

    def _alive_players(self):
        return [p for p in self.players.values() if p.connected and p.name and not p.spectator and p.alive]

    def _all_named_active(self):
        return [p for p in self.players.values() if p.connected and p.name and not p.spectator]

    # ------------------------------------------------------------------ #
    # Game phases
    # ------------------------------------------------------------------ #
    def lobby_phase(self):
        print(f"[server] Listening on {self.host}:{self.port} - waiting for players (min {self.min_players})...")
        while True:
            pid, msg = self.inbound.get()
            if self._handle_common(pid, msg):
                continue
            p = self.players.get(pid)
            if p is None or p.spectator:
                continue
            text = str(msg.get("text", "")).strip()
            lowered = text.lower()
            if p.is_host and lowered == "start":
                active = self._all_named_active()
                if len(active) < self.min_players:
                    self.send_text(p, f"Need at least {self.min_players} players to start (currently {len(active)}).", "red")
                else:
                    self.game_started = True
                    self._log(f"Game started with {len(active)} players: " + ", ".join(x.name for x in active))
                    return
            elif p.is_host and (lowered == "bots" or lowered.startswith("bots ")):
                arg = text[len("bots"):].strip()
                if not arg.isdigit() or not (1 <= int(arg) <= self.MAX_BOTS_PER_REQUEST):
                    self.send_text(p, f"Usage: 'bots <N>' with N from 1 to {self.MAX_BOTS_PER_REQUEST}.", "red")
                else:
                    n = int(arg)
                    error = self.spawn_bots(n)
                    if error:
                        self.send_text(p, f"Couldn't add bots: {error}", "red")
                    else:
                        self.send_text(p, f"Adding {n} bot{'s' if n != 1 else ''} to the lobby...", "cyan")
                        self._log(f"{p.name} added {n} bot(s) to the lobby.")
            else:
                self._broadcast_chat(p, text)

    def assign_roles(self):
        active = self._all_named_active()
        pool = roles.build_role_pool(len(active))
        random.shuffle(pool)
        for p, role in zip(active, pool):
            p.role = role
            p.alive = True

        mafia_names = [p.name for p in active if p.role == roles.ENGINEER]
        for p in active:
            teammates = [n for n in mafia_names if n != p.name] if p.role == roles.ENGINEER else []
            self.send_to(p, {
                "type": "role",
                "role": p.role,
                "description": roles.DESCRIPTIONS[p.role],
                "teammates": teammates,
            })
        self.broadcast_text(f"\nRoles assigned. {len(active)} players in play. Let the game begin!", "bold")
        self._log("Role distribution: " + ", ".join(f"{p.name}={p.role}" for p in active))

    def night_phase(self):
        self.round += 1
        self.broadcast_phase("night", self.round)
        self.broadcast_text(f"\n=== Night {self.round} ===", "blue")

        alive = self._alive_players()
        mafia = [p for p in alive if p.role == roles.ENGINEER]
        doctor = next((p for p in alive if p.role == roles.DOCTOR), None)
        detective = next((p for p in alive if p.role == roles.POLICE), None)
        professors = [p for p in alive if p.role == roles.PROFESSOR]

        mafia_targets = [p for p in alive if p.role != roles.ENGINEER]
        for m in mafia:
            self._prompt(m, "infect", mafia_targets, "Choose a target to infect:", self.NIGHT_TIME)
        if doctor:
            self._prompt(doctor, "save", alive, "Choose a player to protect:", self.NIGHT_TIME)
        for prof in professors:
            self._prompt(prof, "steal", [p for p in alive if p.id != prof.id], "Choose a player to deduct points from:", self.NIGHT_TIME)

        

        if detective:
            invest_targets = [p for p in alive if p.id != detective.id]
            self._prompt(detective, "investigate", invest_targets, "Choose a player to investigate:", self.NIGHT_TIME)

        actors = set(m.id for m in mafia)
        if doctor:
            actors.add(doctor.id)
        if detective:
            actors.add(detective.id)
        for p in alive:
            if p.id not in actors:
                self.send_text(p, "Night falls. Other roles are making their move... sit tight.", "dim")
        for prof in professors:
            actors.add(prof.id)


        infect_votes = {}
        save_target = {}
        pending_pids = set(actors)

        def on_message(pid, msg):
            mtype = msg.get("type")
            consumed = self._handle_common(pid, msg)
            if mtype == "__disconnect__":
                pending_pids.discard(pid)
                return len(pending_pids) == 0
            if consumed:
                return len(pending_pids) == 0

            p = self.players.get(pid)
            if p is None:
                return len(pending_pids) == 0
            if p.pending != "action":
                # free chat from ghosts/idle alive players during the night
                text = str(msg.get("text", "")).strip()
                self._broadcast_chat(p, text)
                return len(pending_pids) == 0

            text = str(msg.get("text", "")).strip()
            ok, target = self._resolve_target(text, p.pending_options)
            if not ok:
                self.send_text(p, "Invalid choice. Enter a number/name from the list, or 'skip'.", "red")
                return len(pending_pids) == 0




            p.pending = None
            pending_pids.discard(pid)
            kind = p.pending_kind
            if kind == "infect" and target:
                infect_votes[pid] = target.id
            elif kind == "save":
                save_target["id"] = target.id if target else None
            elif kind == "investigate" and target:
                is_engineer = target.role == roles.ENGINEER
                self.send_text(
                    p,
                    f"{target.name} is {'an Engineer!' if is_engineer else 'not an Engineer.'}",
                    "red" if is_engineer else "cyan",
                )
            elif kind == "steal" and target:
                target.score-=1; p.score+=1
            return len(pending_pids) == 0
        

        self._pump(time.time() + self.NIGHT_TIME, on_message)
        for p in list(self.players.values()):
            if p.pending == "action":
                p.pending = None

        infect_target_id = self._plurality(list(infect_votes.values()))
        saved_id = save_target.get("id")
        victim = self.players.get(infect_target_id) if infect_target_id else None

        if victim and victim.id != saved_id and victim.role != roles.ENGINEER:
            if self._offer_conversion(victim, mafia):
                victim.role = roles.ENGINEER
                victim.score += self.CONVERT_ACCEPT_BONUS
                self.send_to(victim, {
                    "type": "role", "role": roles.ENGINEER,
                    "description": roles.DESCRIPTIONS[roles.ENGINEER],
                    "teammates": [p.name for p in mafia],
                })
                self.send_text(victim, f"You gain {self.CONVERT_ACCEPT_BONUS} points for joining the Engineers.", "green")
                for e in mafia:
                    self.send_text(e, f"{victim.name} accepted and is now an Engineer!", "red")
            else:
                victim.score -= self.CONVERT_REFUSE_PENALTY
                self.send_text(victim, f"You lose {self.CONVERT_REFUSE_PENALTY} point(s) for refusing the Engineers' offer.", "yellow")
                for e in mafia:
                    self.send_text(e, f"{victim.name} refused to join your team.", "yellow")

        self._log(f"Night {self.round} complete.")

    def day_phase(self):
        self.broadcast_text(f"\n=== Day {self.round} ===", "yellow")

        if self.check_win():
            return

        self.broadcast_phase("day_discuss", self.round)
        self.broadcast_text(
            f"Discussion phase ({self.DAY_DISCUSS_TIME}s). Chat freely, or type "
            "'accuse <name>' to publicly flag a suspect on the suspicion board.",
            "cyan",
        )

        disc_alive_by_name = {p.name.lower(): p for p in self._alive_players()}
        accusations = {}  # accuser_id -> target_id, latest one counts

        def on_discuss(pid, msg):
            consumed = self._handle_common(pid, msg)
            if consumed:
                return False
            p = self.players.get(pid)
            if p is None:
                return False
            text = str(msg.get("text", "")).strip()
            lowered = text.lower()
            if p.alive and not p.spectator and (lowered.startswith("accuse ") or lowered.startswith("!accuse ")):
                target_name = text.split(" ", 1)[1].strip() if " " in text else ""
                target = disc_alive_by_name.get(target_name.lower())
                if target is None or target.id == p.id:
                    self.send_text(p, "Usage: accuse <living player's name> (not yourself).", "red")
                else:
                    accusations[p.id] = target.id
                    tally = Counter(accusations.values())
                    board = ", ".join(
                        f"{self.players[t].name}({c})" for t, c in tally.most_common() if t in self.players
                    )
                    self.broadcast_text(f"[ALERT] {p.name} publicly accuses {target.name}! Suspicion board: {board}", "magenta")
            else:
                self._broadcast_chat(p, text)
            return False

        self._pump(time.time() + self.DAY_DISCUSS_TIME, on_discuss)

        alive = self._alive_players()
        if len(alive) <= 1 or self.check_win():
            return

        self.broadcast_phase("vote", self.round)
        self.broadcast_text(f"Voting phase ({self.DAY_VOTE_TIME}s). Choose who to eliminate.", "magenta")
        for p in alive:
            self._prompt(p, "vote", alive, "Vote to eliminate a player (or 'skip' to abstain):", self.DAY_VOTE_TIME)

        votes = {}
        pending_pids = set(p.id for p in alive)

        def on_vote(pid, msg):
            mtype = msg.get("type")
            consumed = self._handle_common(pid, msg)
            if mtype == "__disconnect__":
                pending_pids.discard(pid)
                return len(pending_pids) == 0
            if consumed:
                return len(pending_pids) == 0

            p = self.players.get(pid)
            if p is None:
                return len(pending_pids) == 0
            if p.pending != "action":
                text = str(msg.get("text", "")).strip()
                self._broadcast_chat(p, text)
                return len(pending_pids) == 0

            text = str(msg.get("text", "")).strip()
            ok, target = self._resolve_target(text, p.pending_options)
            if not ok:
                self.send_text(p, "Invalid choice. Enter a number/name from the list, or 'skip'.", "red")
                return len(pending_pids) == 0

            p.pending = None
            pending_pids.discard(pid)
            if target:
                votes[pid] = target.id
            return len(pending_pids) == 0

        self._pump(time.time() + self.DAY_VOTE_TIME, on_vote)
        for p in list(self.players.values()):
            if p.pending == "action":
                p.pending = None

        vote_values = list(votes.values())
        if vote_values:
            tally = Counter(vote_values)
            top = max(tally.values())
            leaders = [pid for pid, count in tally.items() if count == top]
        else:
            leaders = []

        if len(leaders) == 1:
            eliminated_id = leaders[0]
            self._no_elim_streak = 0
        elif self._no_elim_streak >= 1:
            # Nothing kills at night anymore (Police investigates instead of
            # jailing), so the day vote is the only way the game can end -
            # after a second straight tied/empty day, force a resolution
            # rather than let the game stall forever.
            pool = leaders if leaders else [p.id for p in alive]
            eliminated_id = random.choice(pool)
            self._no_elim_streak = 0
            self.broadcast_text("Two days straight with no decision - the tie is broken at random.", "magenta")
        else:
            self._no_elim_streak += 1
            self.broadcast_text("The vote is tied or inconclusive. No one is eliminated.", "yellow")
            self._log(f"Day {self.round}: no elimination (tie/no votes).")
            return

        victim = self.players.get(eliminated_id)
        if victim is None:
            # Target reconnected under a new id mid-phase and the old id was
            # retired; treat as if the vote fizzled rather than crash.
            self.broadcast_text("The accused is no longer in the game. No one is eliminated.", "yellow")
            self._log(f"Day {self.round}: vote target vanished (stale id).")
            return

        victim.alive = False
        self.broadcast_text(f"{victim.name} has been voted out!", "red")
        if victim.connected:
            self.send_text(victim, "You have been eliminated. You have 15 seconds for last words, seen by everyone:", "yellow")

            def on_last_words(pid, msg):
                mtype = msg.get("type")
                consumed = self._handle_common(pid, msg)
                if mtype == "__disconnect__":
                    return pid == victim.id
                if consumed:
                    return False
                other = self.players.get(pid)
                if other is None:
                    return False
                text = str(msg.get("text", "")).strip()
                if other.id == victim.id:
                    if text:
                        self.broadcast_text(f"{victim.name} (last words): {text}", "magenta")
                    return True
                self._broadcast_chat(other, text)
                return False

            self._pump(time.time() + 15, on_last_words)

        self.broadcast_text(f"{victim.name} was a {victim.role}.", "red")
        self._log(f"Day {self.round}: {victim.name} eliminated ({victim.role}).")

    def check_win(self):
        alive = self._alive_players()
        mafia_alive = [p for p in alive if p.role == roles.ENGINEER]
        good_alive = [p for p in alive if p.role != roles.ENGINEER]
        if not mafia_alive:
            self._end_game("village")
            return True
        if len(mafia_alive) >= len(good_alive):
            self._end_game("mafia")
            return True
        return False

    def _end_game(self, winner):
        self.broadcast_phase("game_over")
        named = [p for p in self.players.values() if p.name and not p.spectator]
        role_list = {p.name: p.role for p in named}
        score_list = {p.name: p.score for p in named}
        # The "game_over" message below carries the same winner + role list and
        # is what every client renders as the final screen - broadcasting the
        # same information again as plain text would just show it twice.
        for p in self.players.values():
            self.send_to(p, {"type": "game_over", "winner": winner, "roles": role_list, "scores": score_list})
        self._log(f"GAME OVER - {winner} wins. Roles: {role_list}. Scores: {score_list}")
        self._write_match_log()

    def _write_match_log(self):
        os.makedirs("match_history", exist_ok=True)
        fname = os.path.join("match_history", f"match_{time.strftime('%Y%m%d_%H%M%S')}.log")
        with open(fname, "w", encoding="utf-8") as f:
            f.write("\n".join(self.log))
        print(f"[server] Match log written to {fname}")
