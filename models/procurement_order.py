from odoo import api, fields, models, tools, registry

import logging
import threading

_logger = logging.getLogger(__name__)


class ProcurementComputeAll(models.TransientModel):
    _inherit = 'procurement.order.compute.all'

    @api.multi
    def _procure_calculation_all(self):
        with api.Environment.manage():
            # As this function is in a new thread, i need to open a new cursor, because the old one may be closed
            new_cr = registry(self._cr.dbname).cursor()
            self = self.with_env(self.env(cr=new_cr))  # TDE FIXME
            scheduler_cron = self.sudo().env.ref('procurement.ir_cron_scheduler_action')
            # Avoid to run the scheduler multiple times in the same time
            try:
                with tools.mute_logger('odoo.sql_db'):
                    self._cr.execute("SELECT id FROM ir_cron WHERE id = %s FOR UPDATE NOWAIT", (scheduler_cron.id,))
            except Exception:
                _logger.info('Attempt to run procurement scheduler aborted, as already running')
                self._cr.rollback()
                self._cr.close()
                return {}

            Procurement = self.env['procurement.order']
            for company in self.env.user.company_ids:
                # Humanytek Fix
                # Procurement.run_scheduler(use_new_cursor=self._cr.dbname, company_id=company.id)
                Procurement.run_scheduler2(use_new_cursor=self._cr.dbname, company_id=company.id)
            # close the new cursor
            self._cr.close()
            return {}


class ProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    # Same as run_scheduler in procurement modules, used to avoid overwrie by stock
    @api.model
    def run_scheduler2(self, use_new_cursor=False, company_id=False):
        """
        Call the scheduler to check the procurement order. This is intented to be done for all existing companies at the same time, so we're running all the methods as SUPERUSER to avoid intercompany and access rights issues.

        @param use_new_cursor: if set, use a dedicated cursor and auto-commit after processing each procurement.
            This is appropriate for batch jobs only.
        @return:  Dictionary of values
        """
        try:
            if use_new_cursor:
                cr = registry(self._cr.dbname).cursor()
                self = self.with_env(self.env(cr=cr))  # TDE FIXME
            ProcurementSudo = self.env['procurement.order'].sudo()
            # Run confirmed procurements
            procurements = ProcurementSudo.search([('state', '=', 'confirmed')] + (company_id and [('company_id', '=', company_id)] or []))
            run_procurements = []
            while procurements:
                procurements.run(autocommit=use_new_cursor)
                run_procurements.extend(procurements.ids)
                if use_new_cursor:
                    self.env.cr.commit()
                procurements = ProcurementSudo.search([('id', 'not in', run_procurements), ('state', '=', 'confirmed')] + (company_id and [('company_id', '=', company_id)] or []))

            # Check done procurements
            procurements = ProcurementSudo.search([('state', '=', 'running')] + (company_id and [('company_id', '=', company_id)] or []))
            procurements.check(autocommit=use_new_cursor)
            if use_new_cursor:
                self.env.cr.commit()

        finally:
            if use_new_cursor:
                try:
                    self.env.cr.close()
                except Exception:
                    pass
        return {}
