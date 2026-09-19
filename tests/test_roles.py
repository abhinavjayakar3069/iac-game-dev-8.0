"""Unit tests for mafia/roles.py - pure logic, no sockets/I-O involved.

Run with: python -m unittest discover tests
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mafia import roles


class ComputeRolesTests(unittest.TestCase):
    def test_rejects_fewer_than_four(self):
        for n in (0, 1, 2, 3):
            with self.assertRaises(ValueError):
                roles.compute_roles(n)

    def test_counts_sum_to_total_for_a_wide_range(self):
        for n in range(4, 30):
            engineer, doctor, police, professor = roles.compute_roles(n)
            self.assertEqual(engineer + doctor + police + professor, n)

    def test_at_least_one_engineer_always(self):
        for n in range(4, 30):
            engineer, _, _, _ = roles.compute_roles(n)
            self.assertGreaterEqual(engineer, 1)

    def test_doctor_present_from_minimum_players(self):
        for n in range(4, 30):
            _, doctor, _, _ = roles.compute_roles(n)
            self.assertEqual(doctor, 1)

    def test_police_only_from_five_players_up(self):
        _, _, police4, _ = roles.compute_roles(4)
        self.assertEqual(police4, 0)
        for n in range(5, 30):
            _, _, police, _ = roles.compute_roles(n)
            self.assertEqual(police, 1)

    def test_non_engineers_never_outnumbered_at_role_assignment(self):
        # The game would be trivially unwinnable if Engineers started already
        # equal to or greater than everyone else.
        for n in range(4, 30):
            engineer, doctor, police, professor = roles.compute_roles(n)
            good = doctor + police + professor
            self.assertLess(engineer, good, f"n={n}: engineer={engineer} good={good}")

    def test_professor_count_never_negative(self):
        for n in range(4, 30):
            _, _, _, professor = roles.compute_roles(n)
            self.assertGreaterEqual(professor, 0)


class BuildRolePoolTests(unittest.TestCase):
    def test_pool_size_matches_player_count(self):
        for n in range(4, 20):
            pool = roles.build_role_pool(n)
            self.assertEqual(len(pool), n)

    def test_pool_contains_only_known_roles(self):
        known = {roles.ENGINEER, roles.DOCTOR, roles.POLICE, roles.PROFESSOR}
        pool = roles.build_role_pool(10)
        self.assertTrue(set(pool).issubset(known))

    def test_every_role_has_a_description(self):
        for role in (roles.ENGINEER, roles.DOCTOR, roles.POLICE, roles.PROFESSOR):
            self.assertIn(role, roles.DESCRIPTIONS)
            self.assertTrue(roles.DESCRIPTIONS[role])


if __name__ == "__main__":
    unittest.main()
