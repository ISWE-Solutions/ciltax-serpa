from odoo import models, fields, api
import requests
import logging
from datetime import datetime
import json
import re
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class AccountMoveReversal(models.TransientModel):
    _inherit = 'account.move.reversal'

    reason = fields.Selection([
        ('01', 'Missing Quantity'),
        ('02', 'Missing Item'),
        ('03', 'Damaged'),
        ('04', 'Wasted'),
        ('05', 'Raw Material Shortage'),
        ('06', 'Refund'),
        ('07', 'Wrong Customer TPIN'),
        ('08', 'Wrong Customer name'),
        ('09', 'Wrong Amount/price'),
        ('10', 'Wrong Quantity'),
        ('11', 'Wrong Item(s)'),
        ('12', 'Wrong tax type'),
        ('13', 'Other reason'),
    ], string='Reason', required=True)

    processed_moves = fields.Boolean(default=False)

    def get_primary_tax(self, partner):
        if partner.tax_id:
            return partner.tax_id[0]
        else:
            credit_move_id = self._context.get('active_id')
            credit_move = self.env['account.move'].browse(credit_move_id)
            move_lines = self.env['account.move.line'].search([('move_id', '=', credit_move.id)])
            for line in move_lines:
                if line.tax_ids:
                    return line.tax_ids[0]
        return None
    def create_credit(self):
        super(AccountMoveReversal, self).create()
        self._process_moves()

    def get_tax_description(self, tax):
        return tax.description if tax else ''

    def get_exchange_rate(self, from_currency, to_currency):
        """Retrieve the latest exchange rate between two currencies."""
        if from_currency == to_currency:
            return 1.0

        rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', from_currency.id),
            ('name', '<=', fields.Date.today())
        ], order='name desc', limit=1)

        if not rate:
            raise ValidationError(f"No exchange rate found for {from_currency.name} to {to_currency.name}.")

        # Assuming ZMW is the company currency, we need to get the inverse rate if needed.
        if to_currency == self.env.company.currency_id:
            return rate.rate

        # If the to_currency is not the company currency, calculate the rate to the company currency and then to the target currency.
        to_rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', to_currency.id),
            ('name', '<=', fields.Date.today())
        ], order='name desc', limit=1)

        if not to_rate:
            raise ValidationError(f"No exchange rate found for {to_currency.name}.")

        return rate.rate / to_rate.rate

    def get_tax_rate(self, tax):
        return tax.amount if tax else 0.0

    def calculate_taxable_amount(self, lines, tax_category):
        filtered_lines = [line for line in lines if
                          self.get_tax_description(self.get_primary_tax(line.partner_id)) == tax_category]
        return round(sum(line.price_subtotal for line in filtered_lines), 2)

    def calculate_tax_amount(self, lines, tax_category):
        filtered_lines = [line for line in lines if
                          self.get_tax_description(self.get_primary_tax(line.partner_id)) == tax_category]
        return round(sum(line.price_total - line.price_subtotal for line in filtered_lines), 2)

    def get_receipt_no(self, invoice):
        _logger.info(f"Fetching receipt number for invoice: {invoice.id}")
        if invoice and hasattr(invoice, 'rcpt_no'):
            _logger.info(f"Receipt number found: {invoice.rcpt_no}")
            return invoice.rcpt_no
        _logger.warning("Receipt number not found.")
        return None

    def calculate_tax_inclusive_price(self, line):
        taxes = line.tax_ids.compute_all(line.price_unit, quantity=1, product=line.product_id,
                                         partner=line.partner_id)
        tax_inclusive_price = taxes['total_included']
        return tax_inclusive_price

    def create_credit_note_payload(self):
        company = self.env.company
        current_user = self.env.user
        # tpin = self.partner_id.tpin if self.partner_id else None
        rcpt_no = self.get_receipt_no(self)
        reversal_reason = self.reason

        credit_move = self.env['account.move'].browse(self._context.get('active_id'))
        partner = credit_move.partner_id

        # Print fetched reversal reason for debugging
        print(f'Fetched Reversal Reason: {reversal_reason}')

        # Fetch the related sale order to get the LPO and export country code
        sale_order = self.env['sale.order'].search([('name', '=', credit_move.invoice_origin)], limit=1)
        lpo = sale_order.lpo if sale_order else None
        export_country_code = sale_order.export_country_id.code if sale_order and sale_order.export_country_id else None

        exchange_rate = self.get_exchange_rate(credit_move.currency_id, self.env.company.currency_id)

        for move in self.move_ids:
            _logger.info(f"Checking move with ID: {move.id} and move type: {move.move_type}")
            tpin = move.partner_id.tpin if move.partner_id else None
            _logger.info(f"Partner ID: {move.partner_id.id if move.partner_id else 'None'}, TPIN: {tpin}")

        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgSdcId": "SDC0010000647",
            "orgInvcNo": credit_move.rcpt_no,
            "cisInvcNo": credit_move.name + '00',
            "custTin": tpin or '1000000000',
            "custNm": credit_move.partner_id.name,
            "salesTyCd": "N",
            "rcptTyCd": "R",
            "pmtTyCd": "01",
            "salesSttsCd": "02",
            "cfmDt": credit_move.invoice_date.strftime('%Y%m%d%H%M%S') if credit_move.invoice_date else None,
            "salesDt": datetime.now().strftime('%Y%m%d'),
            "stockRlsDt": None,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": None,
            "rfdRsnCd": reversal_reason or '01',
            "totItemCnt": len(credit_move.invoice_line_ids),
            "taxblAmtA": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'A'),
            "taxblAmtB": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'B'),
            "taxblAmtC": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'C'),
            "taxblAmtC1": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'C1'),
            "taxblAmtC2": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'C2'),
            "taxblAmtC3": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'C3'),
            "taxblAmtD": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'D'),
            "taxblAmtRvat": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'Rvat'),
            "taxblAmtE": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'E'),
            "taxblAmtF": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'F'),
            "taxblAmtIpl1": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'Ipl1'),
            "taxblAmtIpl2": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'Ipl2'),
            "taxblAmtTl": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'Tl'),
            "taxblAmtEcm": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'Ecm'),
            "taxblAmtExeeg": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'Exeeg'),
            "taxblAmtTot": self.calculate_taxable_amount(credit_move.invoice_line_ids, 'Tot'),
            "taxRtA": 16,
            "taxRtB": 16,
            "taxRtC1": 0.0,
            "taxRtC2": 0.0,
            "taxRtC3": 0.0,
            "taxRtD": 0.0,
            "taxRtRvat": 16,
            "taxRtE": 0.0,
            "taxRtF": 10,
            "taxRtIpl1": 5,
            "taxRtIpl2": 0.0,
            "taxRtTl": 1.5,
            "taxRtEcm": 5,
            "taxRtExeeg": 3,
            "taxRtTot": 0.0,
            "taxAmtA": self.calculate_tax_amount(credit_move.invoice_line_ids, 'A'),
            "taxAmtB": self.calculate_tax_amount(credit_move.invoice_line_ids, 'B'),
            "taxAmtC": self.calculate_tax_amount(credit_move.invoice_line_ids, 'C'),
            "taxAmtC1": self.calculate_tax_amount(credit_move.invoice_line_ids, 'C1'),
            "taxAmtC2": self.calculate_tax_amount(credit_move.invoice_line_ids, 'C2'),
            "taxAmtC3": self.calculate_tax_amount(credit_move.invoice_line_ids, 'C3'),
            "taxAmtD": self.calculate_tax_amount(credit_move.invoice_line_ids, 'D'),
            "taxAmtRvat": self.calculate_tax_amount(credit_move.invoice_line_ids, 'Rvat'),
            "taxAmtE": self.calculate_tax_amount(credit_move.invoice_line_ids, 'E'),
            "taxAmtF": self.calculate_tax_amount(credit_move.invoice_line_ids, 'F'),
            "taxAmtIpl1": self.calculate_tax_amount(credit_move.invoice_line_ids, 'Ipl1'),
            "taxAmtIpl2": self.calculate_tax_amount(credit_move.invoice_line_ids, 'Ipl2'),
            "taxAmtTl": self.calculate_tax_amount(credit_move.invoice_line_ids, 'Tl'),
            "taxAmtEcm": self.calculate_tax_amount(credit_move.invoice_line_ids, 'Ecm'),
            "taxAmtExeeg": self.calculate_tax_amount(credit_move.invoice_line_ids, 'Exeeg'),
            "taxAmtTot": self.calculate_tax_amount(credit_move.invoice_line_ids, 'Tot'),
            "totTaxblAmt": round(sum(line.price_subtotal for line in credit_move.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in credit_move.invoice_line_ids),
                               2),
            "totAmt": round(sum(line.price_total for line in credit_move.invoice_line_ids), 2),
            "prchrAcptcYn": "N",
            "remark": "credit note",
            "regrId": current_user.id,
            "regrNm": current_user.name,
            "modrId": current_user.id,
            "modrNm": current_user.name,
            "saleCtyCd": "1",
            "lpoNumber": lpo or None,
            "currencyTyCd": credit_move.currency_id.name if credit_move.currency_id.name else "ZMW",
            "exchangeRt": str(exchange_rate),
            "destnCountryCd": export_country_code or "ZM",
            "dbtRsnCd": "",
            "invcAdjustReason": "",
            "itemList": [
                {
                    "itemSeq": index + 1,
                    "itemCd": line.product_id.product_tmpl_id.item_Cd,
                    "itemClsCd": line.product_id.product_tmpl_id.item_cls_cd,
                    "itemNm": line.product_id.name,
                    "bcd": line.product_id.barcode,
                    "pkgUnitCd": line.product_id.product_tmpl_id.packaging_unit_cd,
                    "pkg": line.quantity,
                    "qtyUnitCd": line.product_id.product_tmpl_id.quantity_unit_cd,
                    "qty": round(line.quantity, 2),
                    "prc": round(self.calculate_tax_inclusive_price(line), 2),
                    "splyAmt": round(line.quantity * self.calculate_tax_inclusive_price(line), 2),
                    "dcRt": line.discount,
                    "dcAmt": round(line.discount, 2),
                    "isrccCd": "",
                    "isrccNm": "",
                    "isrcRt": 0.0,
                    "isrcAmt": 0.0,
                    "vatCatCd": self.get_tax_description(self.get_primary_tax(partner)),
                    "exciseTxCatCd": None,
                    "vatTaxblAmt": round(line.quantity * line.price_unit, 2),
                    "exciseTaxblAmt": 0.0,
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "exciseTxAmt": 0.0,
                    "totAmt": round(line.quantity * line.price_unit, 2) + round(
                        line.price_total - line.price_subtotal, 2),
                }
                for index, line in enumerate(credit_move.invoice_line_ids)
            ]
        }
        print(payload)
        return payload

    def create_credit_note_api_call(self):
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.sales_endpoint
        payload = self.create_credit_note_payload()
        return self._post_to_api(api_url, payload, "API Response Credit Note")

    def modify_moves(self):
        res = super(AccountMoveReversal, self).modify_moves()
        self._process_moves()
        return res

    def _process_moves(self):
        company = self.env.company
        current_user = self.env.user
        rcpt_no = self.get_receipt_no(self)
        reversal_reason = "01"

        credit_move = self.env['account.move'].browse(self._context.get('active_id'))
        partner = credit_move.partner_id
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)

        # Print fetched reversal reason for debugging
        print(f'Fetched Reversal Reason: {reversal_reason}')

        # Fetch the related sale order to get the LPO and export country code
        sale_order = self.env['sale.order'].search([('name', '=', credit_move.invoice_origin)], limit=1)
        lpo = sale_order.lpo if sale_order else None
        export_country_code = sale_order.export_country_id.code if sale_order and sale_order.export_country_id else None
        for move in self.move_ids:
            _logger.info(f"Checking move with ID: {move.id} and move type: {move.move_type}")
            tpin = move.partner_id.tpin if move.partner_id else None
            _logger.info(f"Partner ID: {move.partner_id.id if move.partner_id else 'None'}, TPIN: {tpin}")

        exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)
        for move in self.move_ids:
            # Process credit note API call
            result_msg = self.create_credit_note_api_call()
            move.message_post(body=f"API Response Credit Note resultMsg: {result_msg}")
            # print(f"API Response Credit Note resultMsg: {result_msg}")

            payload_new_endpoint = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "sarNo": 1,
                "orgSarNo": 0,
                "regTyCd": "M",
                "custTpin": credit_move.partner_id.tpin or "1000000000",
                "custNm": credit_move.partner_id.name if credit_move.partner_id else None,
                "custBhfId": "000",
                "sarTyCd": "03",
                "ocrnDt": credit_move.invoice_date.strftime('%Y%m%d') if credit_move.invoice_date else None,
                "totItemCnt": len(credit_move.invoice_line_ids),
                "totTaxblAmt": round(sum(line.price_subtotal for line in credit_move.invoice_line_ids), 2),
                "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in credit_move.invoice_line_ids), 2),
                "totAmt": round(sum(line.price_total for line in credit_move.invoice_line_ids), 2),
                "remark": 'Credit Note',
                "regrId": current_user.id,
                "regrNm": current_user.name,
                "modrNm": current_user.name,
                "modrId": current_user.id,
                "itemList": [
                    {
                        "itemSeq": index + 1,
                        "itemCd": line.product_id.product_tmpl_id.item_Cd,
                        "itemClsCd": line.product_id.product_tmpl_id.item_cls_cd,
                        "itemNm": line.product_id.name,
                        "bcd": line.product_id.barcode,
                        "pkgUnitCd": line.product_id.product_tmpl_id.packaging_unit_cd,
                        "pkg": line.quantity,
                        "qtyUnitCd": line.product_id.product_tmpl_id.quantity_unit_cd,
                        "qty": line.quantity,
                        "itemExprDt": None,
                        "prc": round(self.calculate_tax_inclusive_price(line), 2),
                        "splyAmt": round(line.quantity * self.calculate_tax_inclusive_price(line), 2),
                        "totDcAmt": 0,
                        "taxblAmt": line.price_subtotal,
                        "vatCatCd": self.get_tax_description(self.get_primary_tax(partner)),
                        "iplCatCd": "IPL1",
                        "tlCatCd": "TL",
                        "exciseTxCatCd": "EXEEG",
                        "vatAmt": round(line.price_total - line.price_subtotal, 2),
                        "iplAmt": 0.0,
                        "tlAmt": 0.0,
                        "exciseTxAmt": 0.0,
                        "taxAmt": round(line.price_total - line.price_subtotal, 2),
                        "totAmt": round(line.price_total, 2)
                    } for index, line in enumerate(credit_move.invoice_line_ids)
                ]
            }
            result_msg_new_endpoint = self._post_to_api(config_settings.stock_io_endpoint,
                                                        payload_new_endpoint, "Save Stock Item API Response")
            move.message_post(body=f"API Response New Endpoint: {result_msg_new_endpoint}")
            # print(f"Save Stock Item API Response: {result_msg_new_endpoint}")

            for line in credit_move.invoice_line_ids:
                # Fetch the available quantity from the stock quant model
                available_quants = self.env['stock.quant'].search([
                    ('product_id', '=', line.product_id.id),
                    ('location_id.usage', '=', 'internal')
                ])
                available_qty = sum(quant.quantity for quant in available_quants)

                remaining_qty = available_qty + line.quantity

            payload_stock = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "regrId": current_user.name,
                "regrNm": current_user.id,
                "modrNm": current_user.name,
                "modrId": current_user.id,
                "stockItemList": [
                    {
                        "itemCd": line.product_id.product_tmpl_id.item_Cd,
                        "rsdQty": remaining_qty
                    } for line in credit_move.invoice_line_ids
                ]
            }
            result_msg_stock = self._post_to_api(config_settings.stock_master_endpoint, payload_stock,
                                                 "Save Stock Master Endpoint response:")
            move.message_post(body=f"Endpoint response: {result_msg_stock}")
            # print(f"Save Stock Master Endpoint response: {result_msg_stock}")

    def _post_to_api(self, url, payload, success_message_prefix):
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            result_msg = response.json().get('resultMsg', 'No result message returned')
            _logger.info(f'{success_message_prefix}: {result_msg}')
            print(f'{success_message_prefix}: {result_msg}')
            return result_msg
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            _logger.error(f'API request failed: {error_msg}')
            print(f'API request failed: {error_msg}')
            return f"Error during API call: {error_msg}"
