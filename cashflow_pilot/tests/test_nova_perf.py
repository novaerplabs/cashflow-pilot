import time

from odoo import fields
from odoo.tests import tagged

from .common import NovaTestCase


@tagged('post_install', '-at_install', 'nova_perf')
class TestNovaPerf(NovaTestCase):
    """NFR-01 / README §16 harness: proves the ≤5s rebuild and cockpit-
    query budgets against a real 10k-open + 50k-settled document volume,
    rather than asserting by vibes (CLAUDE.md §5).

    Deliberately excluded from the default nova_core/nova_pro/nova_bridge
    sweeps - populating 60k posted journal entries is itself slow, so this
    only runs when explicitly requested: `--test-tags nova_perf`.

    The 50k "history" set is 50k real, validly-posted zero-amount invoices
    (amount_residual = 0 the moment they post, no reconciliation needed) -
    a genuine, not faked, accounting state (CLAUDE.md §8) - existing purely
    to prove _sync_move_info's ('amount_residual', '!=', 0) filter and the
    rebuild stay fast against a large total document volume, not just a
    small one that happens to equal the open-document count.
    """

    OPEN_DOC_COUNT = 10000
    HISTORY_DOC_COUNT = 50000
    BATCH_SIZE = 1000
    REBUILD_BUDGET_SECONDS = 5.0
    COCKPIT_BUDGET_SECONDS = 3.0

    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.partner = self.env['res.partner'].create({'name': 'Nova Perf Customer'})
        journal = self.env['account.journal'].sudo().search([
            ('type', 'in', ('bank', 'cash')), ('company_id', '=', self.company.id),
        ], limit=1)
        if not journal:
            journal = self.env['account.journal'].sudo().create({
                'name': 'Nova Perf Bank', 'type': 'bank', 'company_id': self.company.id,
            })
        self.company.nova_journal_ids = [(6, 0, journal.ids)]
        self.today = fields.Date.context_today(self.env['nova.forecast.line'])

    def _batch_post_invoices(self, count, price_unit):
        """Batched create + post in chunks of 1000 (§16) - action_post()
        on a whole recordset at once is far faster than one call per move.
        """
        move_model = self.env['account.move']
        for start in range(0, count, self.BATCH_SIZE):
            batch_count = min(self.BATCH_SIZE, count - start)
            vals_list = [{
                'move_type': 'out_invoice',
                'partner_id': self.partner.id,
                'invoice_date': self.today,
                'invoice_line_ids': [(0, 0, {
                    'name': 'Perf harness line', 'quantity': 1, 'price_unit': price_unit,
                })],
            } for _ in range(batch_count)]
            move_model.create(vals_list).action_post()

    def test_nova_perf_rebuild_and_cockpit_budgets(self):
        self._batch_post_invoices(self.OPEN_DOC_COUNT, price_unit=100.0)
        self._batch_post_invoices(self.HISTORY_DOC_COUNT, price_unit=0.0)
        self._nova_rebaseline_ac10()

        rebuild_start = time.perf_counter()
        self.company.action_refresh_forecast()
        rebuild_elapsed = time.perf_counter() - rebuild_start

        self.assertEqual(
            self.env['nova.move.info'].search_count([
                ('company_id', '=', self.company.id), ('active', '=', True),
            ]),
            self.OPEN_DOC_COUNT,
            "Only the open (non-zero-residual) documents should have live move.info satellites.",
        )
        self.assertLessEqual(
            rebuild_elapsed, self.REBUILD_BUDGET_SECONDS,
            "NFR-01: rebuild must complete within %ss at 10k open docs + 50k history "
            "(measured %.2fs)." % (self.REBUILD_BUDGET_SECONDS, rebuild_elapsed),
        )

        # Server-side contribution to the ≤3s cockpit first-paint budget
        # (NFR-01) - the client-side render itself isn't measurable from a
        # Python test, so this only proves the RPCs the cockpit calls on
        # load are not the bottleneck.
        cockpit_start = time.perf_counter()
        self.env['nova.period.report'].get_cockpit_kpis()
        self.env['nova.period.report'].get_cockpit_grid()
        cockpit_elapsed = time.perf_counter() - cockpit_start

        self.assertLessEqual(
            cockpit_elapsed, self.COCKPIT_BUDGET_SECONDS,
            "NFR-01: cockpit KPI+grid RPCs must return within %ss at this volume "
            "(measured %.2fs)." % (self.COCKPIT_BUDGET_SECONDS, cockpit_elapsed),
        )
