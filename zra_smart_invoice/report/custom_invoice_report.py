from odoo import api, fields, models, _, Command

class CustomReportInvoiceWithoutPayment(models.AbstractModel):
    _name = 'report.zra_smart_invoice.custom_report_invoice'
    _description = 'Custom Account report without payment lines'

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env['account.move'].browse(docids)

        qr_code_urls = {}
        for invoice in docs:
            if invoice.display_qr_code:
                new_code_url = invoice._generate_qr_code(silent_errors=data['report_type'] == 'html')
                if new_code_url:
                    qr_code_urls[invoice.id] = new_code_url

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'custom_docs': docs,
            'qr_code_urls': qr_code_urls,
        }
class CustomInvoice(models.AbstractModel):
    _name = 'report.zra_smart_invoice.custom_report_invoice_with_payments'
    _description = 'Custom Account report with payment lines'
    _inherit = 'report.zra_smart_invoice.custom_report_invoice'

    @api.model
    def _get_report_values(self, docids, data=None):
        rslt = super()._get_report_values(docids, data)
        rslt['report_type'] = data.get('report_type') if data else ''
        return rslt