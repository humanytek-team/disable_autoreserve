from odoo import api, models, registry


class ProcurementOrder(models.Model):
    _inherit = 'procurement.order'

    # Same as run_scheduler in stock module, used to avoid overwrite
    @api.model
    def run_scheduler2(self, use_new_cursor=False, company_id=False):
        """Call the scheduler in order to check the running procurements (super method), to check the minimum stock rules and the availability of moves. This function is intended to be run for all the companies at the same time, so we run functions as SUPERUSER to avoid intercompanies and access rights issues."""
        super(ProcurementOrder, self).run_scheduler(use_new_cursor=use_new_cursor, company_id=company_id)
        try:
            if use_new_cursor:
                cr = registry(self._cr.dbname).cursor()
                self = self.with_env(self.env(cr=cr))  # TDE FIXME

            # Minimum stock rules
            self.sudo()._procure_orderpoint_confirm(use_new_cursor=use_new_cursor, company_id=company_id)

            # Search all confirmed stock_moves and try to assign them
            confirmed_moves = self.env['stock.move'].search([('state', '=', 'confirmed'), ('product_uom_qty', '!=', 0.0)], limit=None, order='priority desc, date_expected asc')
            for x in xrange(0, len(confirmed_moves.ids), 100):
                # TDE CLEANME: muf muf
                # self.env['stock.move'].browse(confirmed_moves.ids[x:x + 100]).action_assign()
                # Humanytek fix
                self.env['stock.move'].browse(confirmed_moves.ids[x:x + 100]).action_assign2()
                if use_new_cursor:
                    self._cr.commit()
            if use_new_cursor:
                self._cr.commit()
        finally:
            if use_new_cursor:
                try:
                    self._cr.close()
                except Exception:
                    pass
        return {}
