from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    tpin = fields.Char(string='TPIN')
    lpo = fields.Char(string='LPO')
    tax_id = fields.Many2one('account.tax', string='Tax')
    bhfId = fields.Char(string='Branch ID')
    orgSdcId = fields.Char(string='Original SdcID')

    vat = fields.Char(string='VAT')  # Assuming you have a vat field in res.partner

    tpin_readonly = fields.Boolean(compute='_compute_readonly_fields', store=True)
    lpo_readonly = fields.Boolean(compute='_compute_readonly_fields', store=True)

    @api.depends('tpin', 'lpo')
    def _compute_readonly_fields(self):
        for record in self:
            record.tpin_readonly = bool(record.lpo)
            record.lpo_readonly = bool(record.tpin)

    @api.onchange('tpin')
    def _onchange_tpin(self):
        self.vat = self.tpin

    @api.onchange('vat')
    def _onchange_vat(self):
        self.tpin = self.vat

    @api.model
    def create(self, vals):
        if 'tpin' in vals:
            vals['vat'] = vals['tpin']
        elif 'vat' in vals:
            vals['tpin'] = vals['vat']
        return super(ResPartner, self).create(vals)

    def write(self, vals):
        if 'tpin' in vals:
            vals['vat'] = vals['tpin']
        elif 'vat' in vals:
            vals['tpin'] = vals['vat']
        return super(ResPartner, self).write(vals)
