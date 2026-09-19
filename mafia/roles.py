"""Role definitions and distribution logic."""

STUDENT = "Student"
GRAD_STUDENT = "Grad Student"
MENTOR = "Mentor"
WARDEN = "Warden"
PROFESSOR = "Professor"


DESCRIPTIONS = {
    STUDENT: (
        "You are a Student. No special ability - vote wisely and pay attention "
        "to who seems suspicious."
    ),
    GRAD_STUDENT: (
        "You are the Grad Student. Each night, choose one other student to "
        "influence. They won't know it happened - they quietly die at the "
        "start of the following night, unless the Mentor protects them "
        "tonight."
    ),
    MENTOR: (
        "You are the Mentor. Each night, choose one player to protect from "
        "the Grad Student's influence. You may protect yourself. Protection "
        "only works against tonight's attempt - it can't save someone "
        "already marked from a previous night."
    ),
    WARDEN: (
        "You are the Warden. Each night, check one player's room. If they're "
        "the Grad Student and were out that night, you'll catch their room "
        "empty - you'll know immediately, and it becomes public the next "
        "morning for everyone to vote on. If not, nothing unusual turns up."
    ),
    PROFESSOR: (
        "You are the Professor. Each night, you can deduct a point from "
        "another player and add it to your own score. You may not deduct "
        "points from yourself."
    ),
}


def compute_roles(n):
    """Return (grad_student, mentor, warden, professor, student) counts for n players."""
    if n < 4:
        raise ValueError("Need at least 4 players")
    grad_student = 1
    mentor = 1
    warden = 1
    professor = 1 if n >= 7 else 0
    student = n - grad_student - mentor - warden - professor
    return grad_student, mentor, warden, professor, student


def build_role_pool(n):
    grad_student, mentor, warden, professor, student = compute_roles(n)
    return (
        [GRAD_STUDENT] * grad_student
        + [MENTOR] * mentor
        + [WARDEN] * warden
        + [PROFESSOR] * professor
        + [STUDENT] * student
    )
