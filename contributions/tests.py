from decimal import Decimal

from django.test import SimpleTestCase

from contributions.reconciliation import contribution_outcome, pledge_outcome


class ContributionOutcomeTests(SimpleTestCase):
    """Pure state machine — no DB required."""

    def _call(self, intended, old_total, payment):
        return contribution_outcome(
            Decimal(str(intended)),
            Decimal(str(old_total)),
            Decimal(str(payment)),
        )

    # ── Status transitions ────────────────────────────────────────────────────

    def test_exact_payment_is_confirmed(self):
        status, total, is_first = self._call(25000, 0, 25000)
        self.assertEqual(status, "confirmed")
        self.assertEqual(total, Decimal("25000"))
        self.assertTrue(is_first)

    def test_underpayment_is_partial(self):
        status, total, is_first = self._call(25000, 0, 10000)
        self.assertEqual(status, "partial")
        self.assertEqual(total, Decimal("10000"))
        self.assertTrue(is_first)

    def test_overpayment_is_overpaid(self):
        status, total, is_first = self._call(25000, 0, 30000)
        self.assertEqual(status, "overpaid")
        self.assertEqual(total, Decimal("30000"))
        self.assertTrue(is_first)

    def test_zero_payment_is_pending(self):
        status, total, is_first = self._call(25000, 0, 0)
        self.assertEqual(status, "pending")
        self.assertTrue(is_first)

    # ── Top-up sequences ──────────────────────────────────────────────────────

    def test_partial_then_remainder_confirms(self):
        status1, total1, _ = self._call(25000, 0, 10000)
        self.assertEqual(status1, "partial")
        status2, total2, is_first2 = self._call(25000, total1, 15000)
        self.assertEqual(status2, "confirmed")
        self.assertEqual(total2, Decimal("25000"))
        self.assertFalse(is_first2)

    def test_partial_then_top_up_overpays(self):
        status1, total1, _ = self._call(25000, 0, 10000)
        status2, total2, _ = self._call(25000, total1, 20000)
        self.assertEqual(status2, "overpaid")
        self.assertEqual(total2, Decimal("30000"))

    def test_second_payment_is_not_first(self):
        _, total1, is_first1 = self._call(25000, 0, 10000)
        _, _, is_first2 = self._call(25000, total1, 5000)
        self.assertTrue(is_first1)
        self.assertFalse(is_first2)

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_one_kobo_short_is_partial(self):
        status, _, _ = self._call("25000.00", 0, "24999.99")
        self.assertEqual(status, "partial")

    def test_one_kobo_over_is_overpaid(self):
        status, _, _ = self._call("25000.00", 0, "25000.01")
        self.assertEqual(status, "overpaid")


class PledgeOutcomeTests(SimpleTestCase):

    def _call(self, pledged, old_total, payment):
        return pledge_outcome(
            Decimal(str(pledged)),
            Decimal(str(old_total)),
            Decimal(str(payment)),
        )

    def test_first_installment_not_complete(self):
        is_complete, total, is_first = self._call(100000, 0, 25000)
        self.assertFalse(is_complete)
        self.assertEqual(total, Decimal("25000"))
        self.assertTrue(is_first)

    def test_final_installment_completes(self):
        is_complete, total, is_first = self._call(100000, 75000, 25000)
        self.assertTrue(is_complete)
        self.assertEqual(total, Decimal("100000"))
        self.assertFalse(is_first)

    def test_overpayment_also_completes(self):
        is_complete, total, _ = self._call(100000, 90000, 20000)
        self.assertTrue(is_complete)
        self.assertEqual(total, Decimal("110000"))

    def test_second_payment_not_first(self):
        _, total1, is_first1 = self._call(100000, 0, 30000)
        _, _, is_first2 = self._call(100000, total1, 30000)
        self.assertTrue(is_first1)
        self.assertFalse(is_first2)
