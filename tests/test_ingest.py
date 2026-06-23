"""Fast unit tests for the ingestion pipeline (stdlib unittest, no GPU/network).

Run from the repo root:

    python -m unittest discover -s tests -t .

These lock in the conversation-building behaviour (chaining, gap-splitting,
group-chat merging, role assignment, ShareGPT mapping) so you don't have to run
the full pipeline to know a change is safe.
"""

import json
import os
import sys
import tempfile
import unittest

# Make the repo root importable when run via `python tests/test_ingest.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest import core, sharegpt
from ingest.adapters import available_sources, get_adapter
from ingest.adapters.telegram import TelegramAdapter

SELF = "Yu Sheng"


def _msg(frm, t, text=None, mtype="message", entities=None):
    msg = {"type": mtype, "from": frm, "date_unixtime": str(t)}
    if entities is not None:
        msg["text"] = entities
        msg["text_entities"] = entities
    else:
        msg["text"] = text
    return msg


def _fixture():
    """Synthetic Telegram export exercising the interesting edge cases."""
    return {
        "personal_information": {"first_name": "Yu", "last_name": "Sheng"},
        "chats": {"list": [
            {"id": 111, "messages": [
                _msg("Alice", 1000, "hey there"),
                _msg("Alice", 1010, "you around?"),                 # chained (10s)
                {"type": "service", "from": "Alice", "date_unixtime": "1012", "text": "pinned"},
                _msg(SELF, 1020, "yeah whats up"),
                _msg(SELF, 1100, "still here"),                     # 80s > 30 -> chain breaks, same role merges
                _msg("Alice", 1200, "cool"),
                _msg("Alice", 6000, "later message"),              # >3600s gap -> new conversation
                _msg(SELF, 6010, entities=[{"type": "plain", "text": "re"},
                                           {"type": "plain", "text": "ply"}]),
            ]},
            {"id": 222, "messages": [                               # group chat, two non-self senders
                _msg("Bob", 2000, "q1"),
                _msg("Carol", 2005, "q2"),                         # different sender, both -> user, merged
                _msg(SELF, 2010, "answer"),
                _msg("Bob", 2020, ""),                             # empty -> invalid, skipped
                _msg(SELF, 2030, "more"),                          # same role -> merged
            ]},
            {"id": 333, "messages": [                               # only self -> dropped (no user turn)
                _msg(SELF, 3000, "talking to myself"),
            ]},
        ]},
    }


def _write_fixture(dir_path):
    path = os.path.join(dir_path, "result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(_fixture(), f, ensure_ascii=False)
    return path


# Golden expected output for the fixture above.
EXPECTED_SHAREGPT = [
    {"conversations": [
        {"from": "human", "value": "hey there\nyou around?"},
        {"from": "gpt", "value": "yeah whats up\nstill here"},
        {"from": "human", "value": "cool"},
    ]},
    {"conversations": [
        {"from": "human", "value": "later message"},
        {"from": "gpt", "value": "reply"},
    ]},
    {"conversations": [
        {"from": "human", "value": "q1\nq2"},
        {"from": "gpt", "value": "answer\nmore"},
    ]},
]


class TelegramAdapterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = _write_fixture(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_detects_self_and_filters_invalid(self):
        msgs = TelegramAdapter().parse(self.path)
        # 8 valid in chat 111 minus 1 service = 7; chat 222 = 4 (empty dropped); chat 333 = 1.
        self.assertEqual(len(msgs), 7 + 4 + 1)
        self.assertTrue(all(m.text for m in msgs))            # no empty text
        self.assertTrue(any(m.sender_is_self for m in msgs))
        self.assertTrue(any(not m.sender_is_self for m in msgs))

    def test_entity_list_text_is_joined(self):
        msgs = TelegramAdapter().parse(self.path)
        reply = [m for m in msgs if m.timestamp == 6010][0]
        self.assertEqual(reply.text, "reply")
        self.assertTrue(reply.sender_is_self)

    def test_self_name_override(self):
        msgs = TelegramAdapter().parse(self.path, self_name="Alice")
        alice = [m for m in msgs if m.sender_id == "Alice"][0]
        self.assertTrue(alice.sender_is_self)


class CoreTest(unittest.TestCase):
    def _samples(self):
        msgs = TelegramAdapter().parse(_write_fixture(tempfile.mkdtemp()))
        return core.build_samples(msgs)

    def test_golden_samples(self):
        samples = self._samples()
        self.assertEqual(sharegpt.to_sharegpt(samples), EXPECTED_SHAREGPT)

    def test_self_only_conversation_dropped(self):
        # chat 333 (only self) must not appear -> exactly 3 samples.
        self.assertEqual(len(self._samples()), 3)

    def test_gap_splits_conversations(self):
        # chat 111 yields two samples because of the >3600s gap.
        samples = self._samples()
        first_two = sharegpt.to_sharegpt(samples)[:2]
        self.assertEqual(first_two, EXPECTED_SHAREGPT[:2])


class ShareGptTest(unittest.TestCase):
    def test_role_mapping_and_drop_one_sided(self):
        samples = [
            [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "yo"}],
            [{"role": "user", "text": "only me"}],                # no assistant -> dropped
            [{"role": "assistant", "text": ""}, {"role": "user", "text": "x"}],  # empty + one-sided -> dropped
        ]
        out = sharegpt.to_sharegpt(samples)
        self.assertEqual(out, [{"conversations": [
            {"from": "human", "value": "hi"}, {"from": "gpt", "value": "yo"}]}])

    def test_jsonl_roundtrip(self):
        samples = [[{"role": "user", "text": "hi"}, {"role": "assistant", "text": "yo"}]]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "out.jsonl")
            sharegpt.write_jsonl(samples, p)
            self.assertEqual(sharegpt.load_jsonl_samples(p), samples)


class RegistryTest(unittest.TestCase):
    def test_telegram_registered(self):
        self.assertIn("telegram", available_sources())
        self.assertEqual(get_adapter("telegram").name, "telegram")

    def test_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            get_adapter("whatsapp")


class CliTest(unittest.TestCase):
    def test_end_to_end_sharegpt(self):
        from ingest.cli import main
        os.environ["DIALOGSMITH_LLM_VALIDATE"] = "false"  # no API calls
        with tempfile.TemporaryDirectory() as d:
            inp = _write_fixture(d)
            out = os.path.join(d, "chat_sharegpt.json")
            rc = main(["--source", "telegram", "--input", inp, "--output", out])
            self.assertEqual(rc, 0)
            with open(out, encoding="utf-8") as f:
                self.assertEqual(json.load(f), EXPECTED_SHAREGPT)

    def test_unknown_source_exit_code(self):
        from ingest.cli import main
        self.assertEqual(main(["--source", "nope"]), 2)


if __name__ == "__main__":
    unittest.main()
