import hashlib

from odoo.tests.common import TransactionCase


class NovaTestCase(TransactionCase):
    """Base test case enforcing AC-10: the product never creates, writes,
    or deletes accounting entries.

    A checksum of all journal entries is captured in setUp() and
    compared again in cleanup for every test method in every subclass.
    Tests that create fixture accounting data (invoices, etc.) via
    normal Odoo APIs should call `self._nova_rebaseline_ac10()` right
    after that fixture setup and before exercising the product code
    under test, so only the product's own actions are checked - AC-10
    is about the product never touching accounting, not about test
    fixtures being forbidden from creating moves.
    """

    def setUp(self):
        super().setUp()
        self._nova_rebaseline_ac10()
        self.addCleanup(self._assert_ac10_invariant)

    def _nova_rebaseline_ac10(self):
        self._nova_ac10_baseline = self._nova_journal_checksum()

    def _nova_journal_checksum(self):
        moves = self.env['account.move'].sudo().search([])
        payload = ','.join(sorted(
            '%s:%s:%s:%s' % (m.id, m.state, m.write_date, m.amount_residual) for m in moves
        )).encode()
        return len(moves), hashlib.sha256(payload).hexdigest()

    def _assert_ac10_invariant(self):
        current = self._nova_journal_checksum()
        self.assertEqual(
            current, self._nova_ac10_baseline,
            "AC-10 violation: journal entries were created, modified, or deleted."
        )
