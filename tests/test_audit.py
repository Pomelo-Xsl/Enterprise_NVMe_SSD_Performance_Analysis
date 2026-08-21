import sqlite3
import unittest

from audit import initialise, recent, record


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        initialise(self.con)

    def test_events_are_serialised_and_newest_first(self):
        record(self.con, "task", "created", "1", {"name": "baseline"})
        record(self.con, "task", "completed", "1")
        events = recent(self.con)
        self.assertEqual(events[0]["action"], "completed")
        self.assertEqual(events[1]["details"]["name"], "baseline")

    def test_limit_is_bounded(self):
        record(self.con, "system", "started", "server")
        self.assertEqual(len(recent(self.con, 0)), 1)


if __name__ == "__main__":
    unittest.main()
