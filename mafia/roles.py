"""Role definitions and distribution logic."""

MAFIA = "Mafia"
DOCTOR = "Doctor"
DETECTIVE = "Detective"
VILLAGER = "Villager"

DESCRIPTIONS = {
    MAFIA: (
        "You are the Mafia. Each night, coordinate with your fellow Mafia "
        "to choose one player to eliminate. You win when the Mafia equal "
        "or outnumber the rest of the village."
    ),
    DOCTOR: (
        "You are the Doctor. Each night, choose one player to protect from "
        "the Mafia's attack. You may protect yourself."
    ),
    DETECTIVE: (
        "You are the Detective. Each night, investigate one player to learn "
        "whether they are Mafia."
    ),
    VILLAGER: (
        "You are a Villager. You have no special power. Use the day's "
        "discussion and your vote to find and eliminate the Mafia."
    ),
}


def compute_roles(n):
    """Return (mafia, doctor, detective, villager) counts for n players."""
    if n < 4:
        raise ValueError("Need at least 4 players")
    mafia = max(1, n // 4)
    doctor = 1
    detective = 1 if n >= 5 else 0
    villager = n - mafia - doctor - detective
    return mafia, doctor, detective, villager


def build_role_pool(n):
    mafia, doctor, detective, villager = compute_roles(n)
    return [MAFIA] * mafia + [DOCTOR] * doctor + [DETECTIVE] * detective + [VILLAGER] * villager
