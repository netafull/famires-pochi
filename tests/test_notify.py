import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401
import notify


def _summary(**kw):
    base = {"new": {}, "ended": {}, "suspected": {}, "blocked": [], "list_failed": [], "errors": [],
            "streaks": {}, "detail_failed": {}}
    base.update(kw)
    return base


class TestNotify(unittest.TestCase):
    def test_no_news_no_message(self):
        self.assertIsNone(notify.build_message(_summary(new={"dennys": 0, "jonathan": 0})))

    def test_new_and_ended(self):
        title, body = notify.build_message(_summary(new={"dennys": 2, "jonathan": 1}, ended={"jonathan": 3}))
        self.assertTrue(title.startswith("ファミレスポチ: "))
        self.assertIn("新メニュー 3件", title)
        self.assertIn("終了 3件", title)
        self.assertIn("デニーズ 2件", body)
        self.assertIn("ジョナサン 3件", body)

    def test_problem_days_in_a_row(self):
        title, body = notify.build_message(_summary(list_failed=["jonathan"], streaks={"jonathan": 3}))
        self.assertIn("巡回に問題(ジョナサン)", title)
        self.assertIn("3日連続", body)

    def test_burst_warning_escalates_at_three_days(self):
        w = notify.build_warnings(_summary(suspected={"dennys": {"count": 25, "threshold": 20, "consecutive_days": 1}}))
        self.assertIn("【警告】デニーズの記録を保留", w[0][0])
        w = notify.build_warnings(_summary(suspected={"dennys": {"count": 25, "threshold": 20, "consecutive_days": 3}}))
        self.assertIn("【要判断】", w[0][0])

    def test_reads_run_summary_and_missing_file(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "run_summary.json"
            p.write_text(json.dumps({"new": {"dennys": 4}, "ended": {}}), encoding="utf-8")
            self.assertEqual(notify.read_run_summary(p)["new"], {"dennys": 4})
            self.assertEqual(notify.read_run_summary(Path(t) / "none.json")["blocked"], [])

    def test_no_topic_does_nothing(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(notify, "send") as s, \
             mock.patch("sys.argv", ["notify.py", "--summary"]):
            self.assertEqual(notify.main(), 0)
            s.assert_not_called()


if __name__ == "__main__":
    unittest.main()
