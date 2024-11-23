import logging

from odoo import models, fields, api
import requests
from odoo.exceptions import ValidationError, UserError
_logger = logging.getLogger()

class ZraSmartInvoice(models.Model):
    _name = 'zra.smart.invoice'
    _description = 'ZRA Smart Invoice Information'

    tpin = fields.Char(string='TPIN', readonly=True)
    bhf_id = fields.Char(string='Branch Office ID', readonly=True)
    device_serial_no = fields.Char(string='Device Serial Number', readonly=True)
    taxpr_nm = fields.Char(string='Taxpayer Name', readonly=True)
    bhf_nm = fields.Char(string='Branch Name', readonly=True)
    loc_desc = fields.Char(string='Location Description', readonly=True)
    province_name = fields.Char(string='Province Name', readonly=True)
    district_name = fields.Char(string='District Name', readonly=True)
    sector_name = fields.Char(string='Sector Name', readonly=True)
    hq_yn = fields.Selection([('Y', 'Yes'), ('N', 'No')], string='Is HQ', readonly=True)
    manager_name = fields.Char(string='Manager Name', readonly=True)
    manager_phone = fields.Char(string='Manager Phone', readonly=True)
    manager_email = fields.Char(string='Manager Email', readonly=True)
    sdc_id = fields.Char(string='SDC ID', readonly=True)
    mrc_no = fields.Char(string='Merchant Registration Number', readonly=True)
    last_purchase_invoice_no = fields.Char(string='Last Purchase Invoice No.', readonly=True)
    last_sale_receipt_no = fields.Char(string='Last Sale Receipt No.', readonly=True)
    last_invoice_no = fields.Char(string='Last Invoice No.', readonly=True)
    last_sale_invoice_no = fields.Char(string='Last Sale Invoice No.', readonly=True)
    last_training_invoice_no = fields.Char(string='Last Training Invoice No.', readonly=True)
    last_proforma_invoice_no = fields.Char(string='Last Proforma Invoice No.', readonly=True)
    last_copy_invoice_no = fields.Char(string='Last Copy Invoice No.', readonly=True)

    def fetch_zra_info(self):
        """Fetch ZRA Smart Invoice information from the API."""
        # Unlink all existing records before fetching new data
        self.unlink()

        # API URL and payload
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        url = config_settings.initialization_endpoint
        company = self.env.company
        if not company.tpin or not company.bhf_id:
            raise ValidationError("TPIN or Branch Office ID is not set for the current company.")

        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "dvcSrlNo": f"{company.tpin}_VSDC"
        }
        try:
            response = requests.post(url, json=payload)
            if response.status_code == 200:
                result = response.json()
                if result.get("resultCd") != "000":
                    raise ValidationError(result.get("resultMsg", "An error occurred while fetching data."))

                # Save data to a new record in the model
                info = result["data"]["info"]
                self.create({
                    'tpin': info.get('tin'),
                    'bhf_id': info.get('bhfId'),
                    'device_serial_no': payload['dvcSrlNo'],
                    'taxpr_nm': info.get('taxprNm'),
                    'bhf_nm': info.get('bhfNm'),
                    'loc_desc': info.get('locDesc'),
                    'province_name': info.get('prvncNm'),
                    'district_name': info.get('dstrtNm'),
                    'sector_name': info.get('sctrNm'),
                    'hq_yn': info.get('hqYn'),
                    'manager_name': info.get('mgrNm'),
                    'manager_phone': info.get('mgrTelNo'),
                    'manager_email': info.get('mgrEmail'),
                    'sdc_id': info.get('sdcId'),
                    'mrc_no': info.get('mrcNo'),
                    'last_purchase_invoice_no': info.get('lastPchsInvcNo'),
                    'last_sale_receipt_no': info.get('lastSaleRcptNo'),
                    'last_invoice_no': info.get('lastInvcNo'),
                    'last_sale_invoice_no': info.get('lastSaleInvcNo'),
                    'last_training_invoice_no': info.get('lastTrainInvcNo'),
                    'last_proforma_invoice_no': info.get('lastProfrmInvcNo'),
                    'last_copy_invoice_no': info.get('lastCopyInvcNo'),
                })
            else:
                raise ValidationError("Failed to connect to API. HTTP Status Code: %s" % response.status_code)
        except Exception as e:
            raise ValidationError("Error fetching data from API: %s" % str(e))

