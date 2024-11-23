from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    tpin = fields.Char(string="TPIN")
    bhf_id = fields.Char(string="Branch ID")
    org_sdc_id = fields.Char(string="Original SDC ID")
