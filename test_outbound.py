import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import outbound as ob  # noqa: E402

DNC = [
    {"name": "Coupang", "aliases": "", "source_type": "case study"},
    {"name": "Volvo", "aliases": "Volvo Group|Volvo Cars", "source_type": "case study"},
    {"name": "Toyota AI", "aliases": "Toyota Research Institute|Toyota", "source_type": "LinkedIn tagline"},
    {"name": "Deep Sentinel", "aliases": "", "source_type": "case study"},
    {"name": "Spot AI", "aliases": "", "source_type": "case study"},
    {"name": "Kapsys", "aliases": "", "level": "block", "source_type": "logo wall"},
    {"name": "Volvo Cars brands", "aliases": "Zenseact", "level": "review",
     "source_type": "owned brand of Volvo Cars"},
    {"name": "Volvo Group brands", "aliases": "Mack Trucks|Nova Bus", "level": "review",
     "source_type": "owned brand of Volvo Group"},
    {"name": "MIT labs", "aliases": "MIT CSAIL", "level": "review", "source_type": "lab of MIT"},
]


class TestDNC(unittest.TestCase):
    def test_exact_customer_with_legal_suffix_is_blocked(self):
        status, _ = ob.check_company("Coupang, Inc.", DNC, {})
        self.assertEqual(status, "BLOCK")

    def test_subsidiary_of_customer_needs_review(self):
        self.assertEqual(ob.check_company("Volvo Autonomous Solutions", DNC, {})[0], "REVIEW")
        self.assertEqual(ob.check_company("Woven Toyota Robotics", DNC, {})[0], "REVIEW")
        self.assertEqual(ob.check_company("Toyota Motor North America", DNC, {})[0], "REVIEW")

    def test_generic_words_do_not_trigger(self):
        # "Deep" and "AI" are generic; these must stay clear
        self.assertEqual(ob.check_company("DeepX Robotics AI", DNC, {})[0], "CLEAR")
        self.assertEqual(ob.check_company("Skild AI", DNC, {})[0], "CLEAR")

    def test_real_targets_clear(self):
        for name in ["Apptronik", "Mind Robotics", "Generalist AI", "Addverb"]:
            self.assertEqual(ob.check_company(name, DNC, {})[0], "CLEAR", name)

    def test_logo_only_customer_is_blocked(self):
        self.assertEqual(ob.check_company("KAPSYS", DNC, {})[0], "BLOCK")

    def test_brand_owned_by_customer_is_held_for_review(self):
        for name in ["Zenseact", "Zenseact AB", "Mack Trucks", "MIT CSAIL"]:
            self.assertEqual(ob.check_company(name, DNC, {})[0], "REVIEW", name)

    def test_brand_rows_do_not_match_on_single_words(self):
        # "Nova Bus" is a Volvo brand, but an unrelated "Nova Robotics" must stay clear
        self.assertEqual(ob.check_company("Nova Robotics", DNC, {})[0], "CLEAR")

    def test_live_page_mention_triggers_review(self):
        pages = {"case-studies": "How Apptronik improved humanoid training with Labellerr"}
        self.assertEqual(ob.check_company("Apptronik", DNC, pages)[0], "REVIEW")


class TestScoring(unittest.TestCase):
    ROW = {"signal_date": "2026-06-01", "signal_types": "funding;data_infra",
           "data_needs": "egocentric;manipulation", "size_band": "scaleup",
           "proof_point": "Coupang (warehouse automation)", "warm_path": "", "india_link": "1"}

    def test_parse_month_only_date(self):
        self.assertEqual(ob.parse_date("2026-01"), dt.date(2026, 1, 1))

    def test_score_is_bounded_and_explainable(self):
        total, tier, parts, _ = ob.score_row(self.ROW, dt.date(2026, 7, 1))
        self.assertEqual(total, sum(parts.values()))
        self.assertLessEqual(total, 100)
        self.assertEqual(tier, "A")

    def test_old_signal_scores_lower(self):
        fresh, *_ = ob.score_row(self.ROW, dt.date(2026, 7, 1))
        stale, *_ = ob.score_row(self.ROW, dt.date(2028, 7, 1))
        self.assertGreater(fresh, stale)


class TestDrafts(unittest.TestCase):
    def test_draft_under_word_limit_and_personalised(self):
        target = {"company": "Acme Robotics", "focus": "humanoid data",
                  "hook": "Saw the Series B announcement last week.",
                  "pain": "teleop capture scales faster than labeling",
                  "proof_point": "Coupang (warehouse automation)"}
        contact = {"name": "Jane Doe", "persona": "technical"}
        subject, body = ob.draft_for(target, contact)
        self.assertIn("Hi Jane", body)
        self.assertIn("Series B", body)
        self.assertIn("Coupang used Labellerr for warehouse automation.", body)
        self.assertLessEqual(ob.word_count(body), ob.MAX_WORDS)
        self.assertTrue(subject.startswith("Acme Robotics"))


class TestRealSnapshot(unittest.TestCase):
    """Runs the committed data through the matcher, so a bad edit to the CSVs fails loudly."""
    ROOT = Path(__file__).resolve().parent.parent

    def test_targets_clear_and_known_brands_caught(self):
        dnc = ob.read_csv(self.ROOT / "data" / "dnc_snapshot.csv")
        for t in ob.read_csv(self.ROOT / "data" / "targets.csv"):
            self.assertEqual(ob.check_company(t["company"], dnc, {})[0], "CLEAR", t["company"])
        expected = {"Coupang Inc": "BLOCK", "Coupang Korea Ltd": "REVIEW", "KAPSYS": "BLOCK", "Kapsys Pte. Ltd.": "BLOCK",
                    "Farfetch": "REVIEW", "Tortuga AgTech": "REVIEW", "MIT CSAIL": "REVIEW",
                    "Lincoln Electric": "CLEAR"}
        for name, status in expected.items():
            self.assertEqual(ob.check_company(name, dnc, {})[0], status, name)


if __name__ == "__main__":
    unittest.main()
