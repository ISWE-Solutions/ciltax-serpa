from odoo import models, fields, api
from odoo.exceptions import ValidationError

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tpin = fields.Char(string='TPIN', size=10)
    export_country_id = fields.Many2one('res.country', string='Export Country')
    lpo = fields.Char(string='LPO')

    @api.constrains('tpin')
    def _check_tpin(self):
        for record in self:
            if record.tpin and not record.tpin.isdigit():
                raise ValidationError('TPIN must contain only numbers.')
            if record.tpin and len(record.tpin) > 10:
                raise ValidationError('TPIN must be at most 10 digits.')

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.tpin = self.partner_id.tpin or ''
            self.lpo = self.partner_id.lpo or ''
            for line in self.order_line:
                if self.partner_id.tax_id:
                    line.tax_id = [(6, 0, [self.partner_id.tax_id.id])]
                else:
                    line.tax_id = False

    def _prepare_invoice(self):
        invoice_vals = super(SaleOrder, self)._prepare_invoice()
        invoice_vals.update({
            'tpin': self.tpin,
            'lpo': self.lpo,
            'export_country_id': self.export_country_id.id,
        })
        return invoice_vals

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('order_id.partner_id')
    def _onchange_partner_id(self):
        if self.order_id.partner_id and self.order_id.partner_id.tax_id:
            self.tax_id = [(6, 0, [self.order_id.partner_id.tax_id.id])]
