"""Unit tests for regex-based sensitive-data detection (stdlib, no network)."""

import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest import redaction, redactor
from ingest.redaction.sg import nric_valid


def _categories(text, locales=None):
    return {f.category for f in redaction.scan_text(text, locales)}


class UniversalTest(unittest.TestCase):
    def test_email(self):
        finds = redaction.scan_text("ping me at john.doe@acme.co please")
        self.assertEqual([f.category for f in finds], ["EMAIL"])
        self.assertEqual(finds[0].preview, "j***@acme.co")  # masked, not raw

    def test_credit_card_luhn(self):
        # Valid Visa test number passes; same length with bad checksum does not.
        self.assertIn("CARD_NUMBER", _categories("card 4111 1111 1111 1111"))
        self.assertNotIn("CARD_NUMBER", _categories("ref 4111 1111 1111 1112"))

    def test_api_keys(self):
        self.assertIn("API_KEY", _categories("token sk-abcdefghij0123456789xyz"))
        self.assertIn("API_KEY", _categories("AKIAIOSFODNN7EXAMPLE"))

    def test_ipv4(self):
        self.assertIn("IP_ADDRESS", _categories("server at 192.168.1.10"))
        self.assertNotIn("IP_ADDRESS", _categories("version 999.999.1.1"))


class SingaporeTest(unittest.TestCase):
    def test_nric_checksum(self):
        # S0000001I is a well-formed example; flipping the suffix must fail.
        self.assertTrue(nric_valid("S0000001I"))
        self.assertFalse(nric_valid("S0000001A"))

    def test_nric_detected_only_when_valid(self):
        self.assertIn("NRIC/FIN", _categories("my ic is S0000001I", ["SG"]))
        self.assertNotIn("NRIC/FIN", _categories("code S0000001A", ["SG"]))

    def test_nric_case_insensitive(self):
        self.assertIn("NRIC/FIN", _categories("ic s0000001i", ["SG"]))

    def test_nric_short_form_requires_context(self):
        # With an NRIC/IC keyword nearby it's flagged...
        self.assertIn("NRIC/FIN (partial)", _categories("NRIC 123A", ["SG"]))
        self.assertIn("NRIC/FIN (partial)", _categories("my IC is 567B", ["SG"]))
        # ...but a bare block/unit number is not.
        self.assertNotIn("NRIC/FIN (partial)", _categories("Blk 123A Clementi", ["SG"]))

    def test_nric_short_form_reports_only_the_id(self):
        finds = [
            f for f in redaction.scan_text("NRIC 123A", ["SG"])
            if f.category == "NRIC/FIN (partial)"
        ]
        self.assertEqual(finds[0].value, "123A")  # keyword excluded from the span

    def test_phone(self):
        self.assertIn("PHONE", _categories("call 9123 4567", ["SG"]))
        self.assertIn("PHONE", _categories("call +65 9123 4567", ["SG"]))

    def test_postal_requires_context_and_not_nric(self):
        self.assertIn("POSTAL_CODE", _categories("Singapore 560123", ["SG"]))
        self.assertIn("POSTAL_CODE", _categories("address S123456", ["SG"]))
        # Must NOT fire on the leading 6 digits of an NRIC.
        self.assertNotIn("POSTAL_CODE", _categories("ic S1234567D", ["SG"]))

    def test_locale_filtering(self):
        # SG detectors don't run when only universal locale is requested.
        self.assertNotIn("NRIC/FIN", _categories("ic S0000001I", []))


class RegistryTest(unittest.TestCase):
    def test_no_duplicate_names(self):
        names = [d.name for d in redaction.iter_detectors()]
        self.assertEqual(len(names), len(set(names)))

    def test_locales_available(self):
        self.assertIn("SG", redaction.available_locales())
        self.assertIn("universal", redaction.available_locales())


class RedactorStageTest(unittest.TestCase):
    def _samples(self):
        return [
            [{"role": "user", "text": "email me at a@b.com"},
             {"role": "assistant", "text": "sure thing"}],
            [{"role": "user", "text": "nothing sensitive here"},
             {"role": "assistant", "text": "ok"}],
        ]

    def test_scan_is_nondestructive_and_reports(self):
        samples = self._samples()
        report = redactor.scan_samples(samples)
        self.assertEqual(report["total_findings"], 1)
        self.assertIn("EMAIL", report["summary"])
        # Original samples untouched.
        self.assertEqual(samples[0][0]["text"], "email me at a@b.com")

    def test_apply_replace_uses_placeholder(self):
        out = redactor.apply(self._samples(), "replace")
        self.assertEqual(out[0][0]["text"], "email me at [EMAIL]")
        self.assertEqual(out[1][0]["text"], "nothing sensitive here")  # untouched

    def test_apply_drop_removes_conversation(self):
        out = redactor.apply(self._samples(), "drop")
        self.assertEqual(len(out), 1)  # the one with an email is dropped
        self.assertEqual(out[0][0]["text"], "nothing sensitive here")


class _FakeClient:
    """Stub OpenAI-compatible client returning a canned JSON body (no network)."""

    def __init__(self, text):
        message = types.SimpleNamespace(content=text)
        resp = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
        completions = types.SimpleNamespace(create=lambda **kw: resp)
        self.chat = types.SimpleNamespace(completions=completions)


class LlmRedactionTest(unittest.TestCase):
    def _samples(self):
        return [[{"role": "user", "text": "hi I'm Alice from Acme"},
                 {"role": "assistant", "text": "hello"}]]

    def test_verbatim_span_is_located_and_masked(self):
        client = _FakeClient(
            '{"findings":[{"turn":0,"text":"Alice","category":"NAME","severity":"high"}]}'
        )
        finds = redactor.llm_scan_samples(self._samples(), client, "model")
        self.assertEqual(len(finds), 1)
        self.assertEqual(finds[0]["category"], "NAME")
        self.assertEqual(finds[0]["start"], 7)  # offset of "Alice"
        self.assertEqual(finds[0]["end"], 12)
        self.assertNotIn("Alice", finds[0]["preview"])  # masked

    def test_unlocatable_span_is_dropped(self):
        # Model paraphrased instead of copying -> can't verify -> skipped.
        client = _FakeClient(
            '{"findings":[{"turn":0,"text":"Bob","category":"NAME","severity":"high"}]}'
        )
        self.assertEqual(redactor.llm_scan_samples(self._samples(), client, "model"), [])

    def test_merge_into_report(self):
        report = redactor.scan_samples(self._samples())  # 0 regex findings
        llm = [{"conversation": 0, "turn": 0, "role": "user", "category": "NAME",
                "severity": "high", "start": 6, "end": 11, "preview": "Al**e"}]
        redactor.merge_llm_findings(report, llm)
        self.assertEqual(report["total_findings"], 1)
        self.assertIn("NAME", report["summary"])
        self.assertNotIn("value", report["findings"][0])  # no raw span persisted

    def test_apply_replace_uses_llm_offsets(self):
        llm = [{"conversation": 0, "turn": 0, "category": "NAME",
                "start": 7, "end": 12}]
        out = redactor.apply(self._samples(), "replace", llm_findings=llm)
        self.assertEqual(out[0][0]["text"], "hi I'm [NAME] from Acme")

    def test_replace_spans_prefers_outer_span(self):
        from ingest.redactor import _replace_spans
        # Partial overlap -> keep the earlier/outer span, one clean replacement.
        self.assertEqual(_replace_spans("abcdef", [(0, 3, "X"), (2, 5, "Y")]), "[X]def")
        # Nested: the inner span must not survive while its enclosing span is
        # dropped (which would leave the uncovered prefix exposed).
        self.assertEqual(
            _replace_spans("a@b.com x", [(0, 7, "EMAIL"), (2, 7, "DOMAIN")]),
            "[EMAIL] x",
        )


if __name__ == "__main__":
    unittest.main()
