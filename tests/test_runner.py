"""Unit tests for the doppelganger runner's pure helpers (no GPU/network/IO).

    python -m unittest discover -s tests -t .
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from doppelganger import steps


class EffectiveBatchTest(unittest.TestCase):
    def test_multiplies_batch_accum_gpus(self):
        cfg = {"per_device_train_batch_size": 2, "gradient_accumulation_steps": 8}
        self.assertEqual(steps.effective_batch(cfg, num_gpus=1), 16)
        self.assertEqual(steps.effective_batch(cfg, num_gpus=4), 64)

    def test_defaults_when_missing(self):
        self.assertEqual(steps.effective_batch({}, num_gpus=1), 1)


class RecommendEpochsTest(unittest.TestCase):
    def test_healthy_midsize_dataset_one_epoch(self):
        # ~3.3k samples, eff batch 16 -> ~208 steps/epoch -> 1 epoch.
        epochs, spe, warnings = steps.recommend_epochs(3324, 16)
        self.assertEqual(epochs, 1)
        self.assertEqual(spe, 208)
        self.assertEqual(warnings, [])

    def test_small_dataset_is_capped_and_warned(self):
        epochs, _, warnings = steps.recommend_epochs(997, 16)
        self.assertLessEqual(epochs, 2)          # capped, not cranked to hit step budget
        self.assertTrue(any("small dataset" in w for w in warnings))

    def test_large_dataset_one_epoch(self):
        epochs, _, warnings = steps.recommend_epochs(20000, 16)
        self.assertEqual(epochs, 1)
        self.assertEqual(warnings, [])

    def test_never_exceeds_cap(self):
        for n in (1200, 1500, 2500, 5000):
            epochs, _, _ = steps.recommend_epochs(n, 16)
            self.assertGreaterEqual(epochs, 1)
            self.assertLessEqual(epochs, steps._MAX_EPOCHS)

    def test_no_dataset_warns(self):
        _, _, warnings = steps.recommend_epochs(0, 16)
        self.assertTrue(warnings)


if __name__ == "__main__":
    unittest.main()
