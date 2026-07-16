from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from desktop_status import StatusSnapshot  # noqa: E402
from desktop_theme import build_status_card_specs, semantic_status_color  # noqa: E402


class DesktopThemeTests(unittest.TestCase):
    def test_build_status_card_specs_maps_snapshot_to_process_cards(self) -> None:
        cards = build_status_card_specs(StatusSnapshot(inbox_count=2, caption_count=3, processed_count=4, output_count=5))

        self.assertEqual([card.key for card in cards], ["inbox", "captions", "processed", "outputs"])
        self.assertEqual([card.title for card in cards], ["Inbox", "Captions", "Processed", "Outputs"])
        self.assertEqual([card.value for card in cards], ["2", "3", "4", "5"])
        self.assertEqual(cards[0].caption, "Ready to process")
        self.assertEqual(cards[2].caption, "Primary finished media")

    def test_semantic_status_color_has_distinct_operational_states(self) -> None:
        self.assertEqual(semantic_status_color("failed"), "#B42318")
        self.assertEqual(semantic_status_color("ready"), "#067647")
        self.assertEqual(semantic_status_color("draft"), "#175CD3")
        self.assertEqual(semantic_status_color("stale_drafts"), "#B54708")
        self.assertEqual(semantic_status_color("unknown"), "#475467")


if __name__ == "__main__":
    unittest.main()
