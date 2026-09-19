"""Role definitions and distribution logic."""

ENGINEER = "Engineer"
DOCTOR = "Doctor"
POLICE = "Police"
PROFESSOR = "Professor"


DESCRIPTIONS = {
    ENGINEER: (
        "You are the Engineer. Each night, you can convert another player into an Engineer."
    ),
    DOCTOR: (
        "You are the Doctor. Each night, choose one player to protect from "
        "the Engineer's attack. You may protect yourself."
    ),
    POLICE: (
        "You are the Police. Each night, you can send one player to the jail thus eliminating them from the game. You may not send yourself to jail."
    ),
    PROFESSOR: (
        "You are the Professor. Each night, you can deduct points from another player because and append them to your score. You may not deduct points from yourself." 
    ),
}


def compute_roles(n):
    """Return (mafia, doctor, detective, villager) counts for n players."""
    if n < 4:
        raise ValueError("Need at least 4 players")
    engineer = max(1, n // 4)
    doctor = 1
    police = 1 if n >= 5 else 0
    professor = n - engineer - doctor - police
    return engineer, doctor, police, professor


def build_role_pool(n):
    engineer, doctor, police, professor = compute_roles(n)
    return [ENGINEER] * engineer + [DOCTOR] * doctor + [POLICE] * police + [PROFESSOR] * professor
