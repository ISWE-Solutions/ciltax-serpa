from odoo import models, fields, api, _
import requests
import logging
from datetime import datetime
import json
import socket
from odoo.exceptions import ValidationError, UserError
import qrcode
import base64
from io import BytesIO

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_type = fields.Char('Sale Type Code', default='N')
    receipt_type = fields.Char('Receipt Type Code', default='S')
    # payment_type = fields.Char('Payment Type Code', default='01')
    sales_status = fields.Char('Sales Status Code', default='02')
    tpin = fields.Char(string='TPIN', size=10)
    export_country_id = fields.Many2one('res.country', string='Export Country')
    export_country_name = fields.Char(string='Export Country Name')
    lpo = fields.Char(string='LPO')
    currency_id = fields.Many2one('res.currency', string='Currency')
    original_invoice_number = fields.Char(string="Original Invoice Number")
    is_printed = fields.Boolean(string="Printed", default=False)
    rcpt_no = fields.Integer(string='Receipt No')
    intrl_data = fields.Char(string='Internal Data')
    rcpt_sign = fields.Char(string='Receipt Sign')
    vsdc_rcpt_pbct_date = fields.Char(string='VSDC Receipt Publish Date')
    sdc_id = fields.Char(string='SDC ID')
    mrc_no = fields.Char(string='MRC No')
    qr_code_url = fields.Char(string='QR Code URL')
    qr_code_image = fields.Char(string='QR Code Image')
    datetime_field = fields.Datetime(string='Date Time', default=fields.Datetime.now)

    def send_to_external_api(self, order_payload):
        sales_url = "http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales"
        stock_url = "http://vsdc.iswe.co.zm/sandbox/trnsStock/saveStock"
        headers = {'Content-Type': 'application/json'}

        try:
            sales_response = requests.post(sales_url, json=order_payload.get('sales_payload'), headers=headers)
            stock_response = requests.post(stock_url, json=order_payload.get('stock_payload'), headers=headers)

            sales_response.raise_for_status()  # Raise HTTPError for bad responses
            stock_response.raise_for_status()  # Raise HTTPError for bad responses

            return {
                'success': True,
                'sales_response': sales_response.json(),
                'stock_response': stock_response.json()
            }
        except requests.RequestException as e:
            return {
                'success': False,
                'error': str(e)
            }

    def get_formatted_vsdc_rcpt_pbct_date(self):
        for record in self:
            if record.vsdc_rcpt_pbct_date:
                try:
                    # Extract and format the date string
                    formatted_date = datetime.strptime(record.vsdc_rcpt_pbct_date, "%Y%m%d%H%M%S").strftime(
                        "%Y-%m-%d %H:%M:%S")
                    return formatted_date
                except ValueError:
                    return "Invalid Date Format"
        return ""

    reversal_reason = fields.Selection([
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
    ], string='Reversal Reason')
    debit_note_reason = fields.Selection([
        ('01', 'Wrong quantity invoiced'),
        ('02', 'Wrong invoice amount'),
        ('03', 'Omitted item'),
        ('04', 'Other [specify]')
    ], string='Debit Note Reason')
    exchange_rate = fields.Char(string='Exchange rate')
    payment_type = fields.Selection([
        ('01', 'CASH'),
        ('02', 'CREDIT'),
        ('03', 'CASH/CREDIT'),
        ('04', 'BANK CHECK'),
        ('05', 'DEBIT&CREDIT CARD'),
        ('06', 'MOBILE MONEY'),
        ('07', 'BANK TRANSFER'),
        ('08', 'OTHER'),
    ], string='Payment Method', required=False, default="01")

    @api.depends('reversal_reason', 'debit_note_reason', 'payment_type')
    def _compute_reason_text(self):
        reversal_reason_dict = dict([
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
        ])

        debit_note_reason_dict = dict([
            ('01', 'Wrong quantity invoiced'),
            ('02', 'Wrong invoice amount'),
            ('03', 'Omitted item'),
            ('04', 'Other [specify]')
        ])

        payment_type_dict = dict([
            ('01', 'CASH'),
            ('02', 'CREDIT'),
            ('03', 'CASH/CREDIT'),
            ('04', 'BANK CHECK'),
            ('05', 'DEBIT&CREDIT CARD'),
            ('06', 'MOBILE MONEY'),
            ('07', 'BANK TRANSFER'),
            ('08', 'OTHER')
        ])

        for record in self:
            record.reversal_reason_text = reversal_reason_dict.get(record.reversal_reason, "")
            record.debit_note_reason_text = debit_note_reason_dict.get(record.debit_note_reason, "")
            record.payment_type_text = payment_type_dict.get(record.payment_type, "")

    reversal_reason_text = fields.Char(string='Reversal Reason Text', compute='_compute_reason_text')
    debit_note_reason_text = fields.Char(string='Debit Note Reason Text', compute='_compute_reason_text')
    payment_type_text = fields.Char(string='Payment Type', compute='_compute_reason_text')

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
            # If there's a related sale order, get the TPIN and LPO from there
            sale_orders = self.env['sale.order'].search([('partner_id', '=', self.partner_id.id)], limit=1)
            if sale_orders:
                sale_order = sale_orders[0]
                self.tpin = sale_order.tpin or ''
                self.lpo = sale_order.lpo or ''
                self.export_country_id = sale_order.export_country_id or False

            # Otherwise, use partner's default information if available
            if not self.tpin:
                self.tpin = self.partner_id.tpin or ''
            if not self.lpo:
                self.lpo = self.partner_id.lpo or ''

            # Set taxes based on partner's default tax settings if applicable
            for line in self.invoice_line_ids:
                if self.partner_id.tax_id:
                    line.tax_ids = [(6, 0, [self.partner_id.tax_id.id])]
                else:
                    line.tax_ids = False

    def action_print_custom_invoice(self):
        return self.env.ref('zra_smart_invoice.custom_account_invoices').report_action(self)

    def action_print_custom_invoice_url(self):
        report_url = f'/report/pdf/zra_smart_invoice.custom_account_invoices/{self.id}'
        return {'success': True, 'report_url': report_url}

    @api.model
    def generate_qr_code_button(self):
        for record in self:
            if record.qr_code_url:
                try:
                    qr = qrcode.QRCode(
                        version=1,
                        error_correction=qrcode.constants.ERROR_CORRECT_L,
                        box_size=10,
                        border=4,
                    )
                    qr.add_data(record.qr_code_url)
                    qr.make(fit=True)

                    img = qr.make_image(fill='black', back_color='white')
                    buffer = BytesIO()
                    img.save(buffer, format="PNG")
                    qr_code_image_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

                    record.write({'qr_code_image': qr_code_image_base64})
                    print(f'QR Code image saved for record {record.id}')
                except Exception as e:
                    print(f'Failed to generate QR Code for record {record.id}: {str(e)}')
            else:
                record.write({'qr_code_image': False})
                # print(f'No QR Code URL for record {record.id}')

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

        if to_currency == self.env.company.currency_id:
            return rate.inverse_company_rate

        to_rate = self.env['res.currency.rate'].search([
            ('currency_id', '=', to_currency.id),
            ('name', '<=', fields.Date.today())
        ], order='name desc', limit=1)

        if not to_rate:
            raise ValidationError(f"No exchange rate found for {to_currency.name}.")

        return rate.inverse_company_rate / to_rate.inverse_company_rate

    def get_primary_tax(self, partner):
        if partner.tax_id:
            return partner.tax_id[0]
        else:
            move_lines = self.env['account.move.line'].search([('move_id', '=', self.id)])
            for line in move_lines:
                if line.tax_ids:
                    return line.tax_ids[0]
        return None

    def get_tax_description(self, tax):
        if tax:
            return tax.description or ""
        return ""

    def get_tax_rate(self, tax):
        return tax.amount if tax else 0.0

    def calculate_custom_subtotal(self):
        custom_subtotal = 0.0
        for line in self.invoice_line_ids:
            custom_subtotal += line.quantity * line.price_unit
        return custom_subtotal

    def calculate_taxable_amount(self, lines, tax_category):
        total_amount = 0.0
        for line in lines:
            tax_description = self.get_tax_description(line.tax_ids)
            if tax_category in tax_description:
                total_amount += line.price_subtotal
        return total_amount

    def calculate_tax_amount(self, lines, tax_category):
        filtered_lines = [line for line in lines if
                          self.get_tax_description(self.get_primary_tax(self.partner_id)) == tax_category]
        return round(sum(line.price_total - line.price_subtotal for line in filtered_lines), 2)

    def calculate_tax_inclusive_price(self, line):
        taxes = line.tax_ids.compute_all(line.price_unit, quantity=1, product=line.product_id, partner=self.partner_id)
        tax_inclusive_price = taxes['total_included']
        return tax_inclusive_price

    def get_sales_order_fields(self):
        """Retrieve tpin, lpo, and export_country_id from related sale order."""
        sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
        return sale_order.tpin, sale_order.lpo, sale_order.export_country_id.code if sale_order.export_country_id else None

    def action_post(self):
        res = super(AccountMove, self).action_post()

        if self.move_type in ['out_invoice', 'out_refund', 'in_refund']:
            tpin, lpo, export_country_code = self.get_sales_order_fields()
            export_country = self.env['res.country'].search([('code', '=', export_country_code)], limit=1)
            export_country_name = export_country.name if export_country else None

            self.write({
                'lpo': lpo,
                'export_country_id': export_country.id if export_country else None,
                'export_country_name': export_country_name
            })

            if self.currency_id.name != 'ZMW':
                exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)
                self.write({
                    'exchange_rate': round(exchange_rate, 2)
                })

            # Check if any product in the invoice is a service
            has_service_product = any(line.product_id.detailed_type == 'service' for line in self.invoice_line_ids)

            if has_service_product:
                # If the product is a service, call the stock endpoints
                payload_stock_items = self.generate_stock_payload_items()
                self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stock/saveStockItems', payload_stock_items,
                                        "Save Stock Item API Response")

                payload_stock_master = self.generate_stock_payload_master()
                self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stockMaster/saveStockMaster', payload_stock_master,
                                        "Stock Master API Response")

            else:
                # If the product is not a service, call the sales endpoint
                if self.move_type == 'out_invoice':
                    payload = self.generate_sales_payload()
                    self._post_to_api("http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales", payload, "Save Sales API Response")
                elif self.move_type == 'out_refund':
                    if not self._is_internet_connected():
                        raise UserError("Cannot perform credit note offline. Please check your internet connection.")

                    payload = self.credit_note_payload()
                    self._post_to_api("http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales", payload,
                                      "Save Credit Note API Response resultMsg")

                    reversal_id = self._context.get('active_id')
                    reversal_move = self.env['account.move.reversal'].browse(reversal_id)
                    reversal_reason = reversal_move.reason if reversal_move else "01"
                    self.write({'reversal_reason': reversal_reason})
                elif self.move_type == 'in_refund':
                    original_ref = self.ref
                    payload = self.debit_note_payload(original_ref)
                    self._post_to_api("http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales", payload,
                                      "Save Debit Note API Response resultMsg")

                    debit_reversal_id = self._context.get('active_id')
                    debit_reversal_move = self.env['account.debit.note'].browse(debit_reversal_id)
                    debit_note_reason = debit_reversal_move.reason if debit_reversal_move else "01"
                    self.write({'debit_note_reason': debit_note_reason})

            for invoice in self:
                if invoice.move_type == 'out_invoice' and invoice.invoice_origin:
                    pickings = self.env['stock.picking'].search([
                        ('origin', '=', invoice.invoice_origin),
                        ('state', 'in', ['confirmed', 'assigned'])
                    ])
                    for picking in pickings:
                        picking.action_confirm()
                        picking.action_assign()
                        picking.button_validate()
                else:
                    self._accounting_update_stock_quantities(invoice)

                if invoice.move_type == 'out_refund':
                    self._update_stock_quantities(invoice)

                if invoice.move_type == 'in_refund':
                    self._debit_update_stock_quantities(invoice)

            self.generate_qr_code_button()

        return res

    def _is_internet_connected(self):
        try:
            # Try to connect to a reliable public host
            socket.create_connection(("8.8.8.8", 53))
            return True
        except OSError:
            return False

    def _accounting_update_stock_quantities(self, invoice):
        for line in invoice.invoice_line_ids:
            product = line.product_id
            if not product:  # Skip lines without a product
                continue
            quantity = line.quantity
            stock_quant = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id.usage', '=', 'internal')
            ], limit=1)

            if stock_quant:
                stock_quant.quantity -= quantity
            else:
                # If no stock_quant is found, create a new one
                self.env['stock.quant'].create({
                    'product_id': product.id,
                    'location_id': self.env['stock.location'].search([('usage', '=', 'internal')], limit=1).id,
                    'quantity': -quantity,  # Deduct the quantity
                })

    def _update_stock_quantities(self, invoice):
        for line in invoice.invoice_line_ids:
            product = line.product_id
            if not product:  # Skip lines without a product
                continue
            quantity = line.quantity
            stock_quant = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id.usage', '=', 'internal')
            ], limit=1)

            if stock_quant:
                stock_quant.quantity += quantity
            else:
                # If no stock_quant is found, create a new one
                self.env['stock.quant'].create({
                    'product_id': product.id,
                    'location_id': self.env['stock.location'].search([('usage', '=', 'internal')], limit=1).id,
                    'quantity': quantity,
                })

    def _debit_update_stock_quantities(self, invoice):
        for line in invoice.invoice_line_ids:
            product = line.product_id
            if not product:  # Skip lines without a product
                continue
            quantity = line.quantity
            stock_quant = self.env['stock.quant'].search([
                ('product_id', '=', product.id),
                ('location_id.usage', '=', 'internal')
            ], limit=1)

            if stock_quant:
                stock_quant.quantity -= quantity
            else:
                # If no stock_quant is found, create a new one
                self.env['stock.quant'].create({
                    'product_id': product.id,
                    'location_id': self.env['stock.location'].search([('usage', '=', 'internal')], limit=1).id,
                    'quantity': -quantity,  # Deduct the quantity
                })

    def generate_sales_payload(self):
        current_user = self.env.user
        company = self.env.company
        tpin, lpo, export_country_code = self.get_sales_order_fields()
        exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgInvcNo": 0,
            "cisInvcNo": self.name + "INV",
            "custTpin": tpin or "1000000000",
            "custNm": self.partner_id.name,
            "salesTyCd": self.sale_type or 'N',
            "rcptTyCd": self.receipt_type or 'S',
            "pmtTyCd": self.payment_type,
            "salesSttsCd": self.sales_status or '02',
            "cfmDt": self.invoice_date.strftime('%Y%m%d%H%M%S') if self.invoice_date else None,
            "salesDt": datetime.now().strftime('%Y%m%d'),
            "stockRlsDt": None,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": None,
            "rfdRsnCd": "",
            "totItemCnt": len(self.invoice_line_ids),
            "taxblAmtA": self.calculate_taxable_amount(self.invoice_line_ids, 'A'),
            "taxblAmtB": self.calculate_taxable_amount(self.invoice_line_ids, 'B'),
            "taxblAmtC": self.calculate_taxable_amount(self.invoice_line_ids, 'C'),
            "taxblAmtC1": self.calculate_taxable_amount(self.invoice_line_ids, 'C1'),
            "taxblAmtC2": self.calculate_taxable_amount(self.invoice_line_ids, 'C2'),
            "taxblAmtC3": self.calculate_taxable_amount(self.invoice_line_ids, 'C3'),
            "taxblAmtD": self.calculate_taxable_amount(self.invoice_line_ids, 'D'),
            "taxblAmtRvat": self.calculate_taxable_amount(self.invoice_line_ids, 'RVAT'),
            "taxblAmtE": self.calculate_taxable_amount(self.invoice_line_ids, 'E'),
            "taxblAmtF": self.calculate_taxable_amount(self.invoice_line_ids, 'F'),
            "taxblAmtIpl1": self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl1'),
            "taxblAmtIpl2": self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl2'),
            "taxblAmtTl": self.calculate_taxable_amount(self.invoice_line_ids, 'Tl'),
            "taxblAmtEcm": self.calculate_taxable_amount(self.invoice_line_ids, 'Ecm'),
            "taxblAmtExeeg": self.calculate_taxable_amount(self.invoice_line_ids, 'Exeeg'),
            "taxblAmtTot": self.calculate_taxable_amount(self.invoice_line_ids, 'Tot'),
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
            "taxAmtA": self.calculate_tax_amount(self.invoice_line_ids, 'A'),
            "taxAmtB": self.calculate_tax_amount(self.invoice_line_ids, 'B'),
            "taxAmtC": self.calculate_tax_amount(self.invoice_line_ids, 'C'),
            "taxAmtC1": self.calculate_tax_amount(self.invoice_line_ids, 'C1'),
            "taxAmtC2": self.calculate_tax_amount(self.invoice_line_ids, 'C2'),
            "taxAmtC3": self.calculate_tax_amount(self.invoice_line_ids, 'C3'),
            "taxAmtD": self.calculate_tax_amount(self.invoice_line_ids, 'D'),
            "taxAmtRvat": self.calculate_tax_amount(self.invoice_line_ids, 'Rvat'),
            "taxAmtE": self.calculate_tax_amount(self.invoice_line_ids, 'E'),
            "taxAmtF": self.calculate_tax_amount(self.invoice_line_ids, 'F'),
            "taxAmtIpl1": self.calculate_tax_amount(self.invoice_line_ids, 'Ipl1'),
            "taxAmtIpl2": self.calculate_tax_amount(self.invoice_line_ids, 'Ipl2'),
            "taxAmtTl": self.calculate_tax_amount(self.invoice_line_ids, 'Tl'),
            "taxAmtEcm": self.calculate_tax_amount(self.invoice_line_ids, 'Ecm'),
            "taxAmtExeeg": self.calculate_tax_amount(self.invoice_line_ids, 'Exeeg'),
            "taxAmtTot": self.calculate_tax_amount(self.invoice_line_ids, 'Tot'),
            "totTaxblAmt": round(sum(line.price_subtotal for line in self.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in self.invoice_line_ids), 2),
            "totAmt": round(sum(line.price_total for line in self.invoice_line_ids), 2),
            "prchrAcptcYn": "N",
            "remark": "sales",
            "regrId": current_user.id,
            "regrNm": current_user.name,
            "modrId": current_user.id,
            "modrNm": current_user.name,
            "saleCtyCd": "1",
            "lpoNumber": lpo or None,
            "currencyTyCd": self.currency_id.name if self.currency_id.name else "ZMW",
            "exchangeRt": str(round(exchange_rate, 2)),
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
                    "qty": line.quantity,
                    "prc": round(self.calculate_tax_inclusive_price(line), 2),
                    "splyAmt": round(line.quantity * self.calculate_tax_inclusive_price(line), 2),
                    "dcRt": line.discount,
                    "dcAmt": round((line.quantity * self.calculate_tax_inclusive_price(line)) * (line.discount / 100),
                                   2),
                    "isrccCd": "",
                    "isrccNm": "",
                    "isrcRt": 0.0,
                    "isrcAmt": 0.0,
                    "vatCatCd": self.get_tax_description(line.tax_ids),
                    "exciseTxCatCd": None,
                    "vatTaxblAmt": round(line.price_subtotal, 2),
                    "exciseTaxblAmt": 0.0,
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "exciseTxAmt": 0.0,
                    "totAmt": round(line.price_total, 2),
                }
                for index, line in enumerate(self.invoice_line_ids)
            ]
        }

        # Additional payloads for stock items and stock master
        payload_stock_items = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": tpin or "1000000000",
            "custNm": self.partner_id.name,
            "custBhfId": "000",
            "sarTyCd": "11",
            "ocrnDt": self.invoice_date.strftime('%Y%m%d') if self.invoice_date else None,
            "totItemCnt": len(self.invoice_line_ids),
            "totTaxblAmt": round(sum(line.price_subtotal for line in self.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in self.invoice_line_ids), 2),
            "totAmt": round(sum(line.price_total for line in self.invoice_line_ids), 2),
            "remark": 'Sales',
            "regrId": current_user.name,
            "regrNm": current_user.id,
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
                    # Example static value, can be dynamic
                    "pkg": line.quantity,
                    "qtyUnitCd": line.product_id.product_tmpl_id.quantity_unit_cd,
                    "qty": line.quantity,
                    "itemExprDt": None,
                    "prc": round(line.price_unit, 2),
                    "splyAmt": round(line.quantity * self.calculate_tax_inclusive_price(line), 2),
                    "totDcAmt": 0,
                    "vatCatCd": self.get_tax_description(line.tax_ids),
                    "exciseTxCatCd": "EXEEG",
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "taxblAmt": 0,
                    "iplAmt": 0,
                    "tlAmt": 0,
                    "exciseTxAmt": 0,
                    "taxAmt": round(line.price_total - line.price_subtotal, 2),
                    "totAmt": round((line.quantity * line.price_unit) + round(
                        line.price_total - line.price_subtotal, 2), 2),
                } for index, line in enumerate(self.invoice_line_ids)
            ]
        }

        self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stock/saveStockItems', payload_stock_items,
                                "Save Stock Item API Response Endpoint")

        payload_stock_master = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "regrId": current_user.name,
            "regrNm": current_user.id,
            "modrNm": current_user.name,
            "modrId": current_user.id,
            "stockItemList": [
                {
                    "itemCd": line.product_id.product_tmpl_id.item_Cd,
                    # Calculate available_qty and remaining_qty for each item
                    "rsdQty": sum(quant.quantity for quant in self.env['stock.quant'].search([
                        ('product_id', '=', line.product_id.id),
                        ('location_id.usage', '=', 'internal')
                    ])) - line.quantity
                } for index, line in enumerate(self.invoice_line_ids)
            ]
        }

        self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stockMaster/saveStockMaster', payload_stock_master,
                                "Stock Master Endpoint response")

        return payload

    def generate_stock_payload_items(self):
        current_user = self.env.user
        company = self.env.company
        payload_stock_items = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": self.partner_id.tpin or "1000000000",
            "custNm": self.partner_id.name,
            "custBhfId": "000",
            "sarTyCd": "11",
            "ocrnDt": self.invoice_date.strftime('%Y%m%d') if self.invoice_date else None,
            "totItemCnt": len(self.invoice_line_ids),
            "totTaxblAmt": round(sum(line.price_subtotal for line in self.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in self.invoice_line_ids), 2),
            "totAmt": round(sum(line.price_total for line in self.invoice_line_ids), 2),
            "remark": 'Sales',
            "regrId": current_user.name,
            "regrNm": current_user.id,
            "modrNm": current_user.name,
            "modrId": current_user.id,
            "itemList": [
                {
                    "itemSeq": index + 1,
                    "itemCd": line.product_id.default_code,
                    "itemNm": line.product_id.name,
                    "qty": line.quantity,
                    "prc": round(line.price_unit, 2),
                    "splyAmt": round(line.quantity * line.price_unit, 2),
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "totAmt": round(line.price_total, 2),
                } for index, line in enumerate(self.invoice_line_ids)
            ]
        }
        return payload_stock_items

    def generate_stock_payload_master(self):
        current_user = self.env.user
        company = self.env.company
        payload_stock_master = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "regrId": current_user.name,
            "regrNm": current_user.id,
            "modrNm": current_user.name,
            "modrId": current_user.id,
            "stockItemList": [
                {
                    "itemCd": line.product_id.default_code,
                    "rsdQty": sum(quant.quantity for quant in self.env['stock.quant'].search([
                        ('product_id', '=', line.product_id.id),
                        ('location_id.usage', '=', 'internal')
                    ])) - line.quantity
                } for line in self.invoice_line_ids
            ]
        }
        return payload_stock_master

    # ==============================================================================================
    #                                          CREDIT NOTE
    # ==============================================================================================

    def get_receipt_no(self, invoice):
        print(f"Fetching receipt number for invoice: {invoice.id}")
        if invoice and hasattr(invoice, 'rcpt_no'):
            print(f"Receipt number found: {invoice.rcpt_no}")
            return invoice.rcpt_no
        _logger.warning("Receipt number not found.")
        return None

    def credit_note_payload(self):

        current_user = self.env.user
        company = self.env.company
        # tpin = self.partner_id.tpin if self.partner_id else None
        tpin, lpo, export_country_code = self.get_sales_order_fields()
        rcpt_no = self.get_receipt_no(self)
        print(rcpt_no)
        credit_move = self.env['account.move'].browse(self._context.get('active_id'))
        partner = credit_move.partner_id
        print('Credit Id', credit_move)
        # Retrieve the active record for account.move.reversal
        reversal_id = self._context.get('active_id')
        reversal_move = self.env['account.move.reversal'].browse(reversal_id)
        reversal_reason = reversal_move.reason if reversal_move else "01"
        print(f'Fetched Reversal Reason: {reversal_reason}')

        # Fetch the related sale order to get the LPO and export country code
        sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
        lpo = sale_order.lpo if sale_order else None
        export_country_code = sale_order.export_country_id.code if sale_order and sale_order.export_country_id else None

        exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)

        api_url = "http://vsdc.iswe.co.zm/sandbox/trnsSales/saveSales"
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgSdcId": company.org_sdc_id,
            "orgInvcNo": rcpt_no,
            "cisInvcNo": self.name + '-0',
            "custTpin": tpin or '1000000000',
            "custNm": self.partner_id.name,
            "salesTyCd": "N",
            "rcptTyCd": "R",
            "pmtTyCd": "01",
            "salesSttsCd": "02",
            "cfmDt": self.invoice_date.strftime('%Y%m%d%H%M%S') if self.invoice_date else None,
            "salesDt": datetime.now().strftime('%Y%m%d'),
            "stockRlsDt": None,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": None,
            "rfdRsnCd": reversal_reason or '01',
            "totItemCnt": len(self.invoice_line_ids),
            "taxblAmtA": self.calculate_taxable_amount(self.invoice_line_ids, 'A'),
            "taxblAmtB": self.calculate_taxable_amount(self.invoice_line_ids, 'B'),
            "taxblAmtC": self.calculate_taxable_amount(self.invoice_line_ids, 'C'),
            "taxblAmtC1": self.calculate_taxable_amount(self.invoice_line_ids, 'C1'),
            "taxblAmtC2": self.calculate_taxable_amount(self.invoice_line_ids, 'C2'),
            "taxblAmtC3": self.calculate_taxable_amount(self.invoice_line_ids, 'C3'),
            "taxblAmtD": self.calculate_taxable_amount(self.invoice_line_ids, 'D'),
            "taxblAmtRvat": self.calculate_taxable_amount(self.invoice_line_ids, 'Rvat'),
            "taxblAmtE": self.calculate_taxable_amount(self.invoice_line_ids, 'E'),
            "taxblAmtF": self.calculate_taxable_amount(self.invoice_line_ids, 'F'),
            "taxblAmtIpl1": self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl1'),
            "taxblAmtIpl2": self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl2'),
            "taxblAmtTl": self.calculate_taxable_amount(self.invoice_line_ids, 'Tl'),
            "taxblAmtEcm": self.calculate_taxable_amount(self.invoice_line_ids, 'Ecm'),
            "taxblAmtExeeg": self.calculate_taxable_amount(self.invoice_line_ids, 'Exeeg'),
            "taxblAmtTot": self.calculate_taxable_amount(self.invoice_line_ids, 'Tot'),
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
            "taxAmtA": self.calculate_tax_amount(self.invoice_line_ids, 'A'),
            "taxAmtB": self.calculate_tax_amount(self.invoice_line_ids, 'B'),
            "taxAmtC": self.calculate_tax_amount(self.invoice_line_ids, 'C'),
            "taxAmtC1": self.calculate_tax_amount(self.invoice_line_ids, 'C1'),
            "taxAmtC2": self.calculate_tax_amount(self.invoice_line_ids, 'C2'),
            "taxAmtC3": self.calculate_tax_amount(self.invoice_line_ids, 'C3'),
            "taxAmtD": self.calculate_tax_amount(self.invoice_line_ids, 'D'),
            "taxAmtRvat": self.calculate_tax_amount(self.invoice_line_ids, 'Rvat'),
            "taxAmtE": self.calculate_tax_amount(self.invoice_line_ids, 'E'),
            "taxAmtF": self.calculate_tax_amount(self.invoice_line_ids, 'F'),
            "taxAmtIpl1": self.calculate_tax_amount(self.invoice_line_ids, 'Ipl1'),
            "taxAmtIpl2": self.calculate_tax_amount(self.invoice_line_ids, 'Ipl2'),
            "taxAmtTl": self.calculate_tax_amount(self.invoice_line_ids, 'Tl'),
            "taxAmtEcm": self.calculate_tax_amount(self.invoice_line_ids, 'Ecm'),
            "taxAmtExeeg": self.calculate_tax_amount(self.invoice_line_ids, 'Exeeg'),
            "taxAmtTot": self.calculate_tax_amount(self.invoice_line_ids, 'Tot'),
            "totTaxblAmt": round(sum(line.price_subtotal for line in self.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in self.invoice_line_ids),
                               2),
            "totAmt": round(sum(line.price_total for line in self.invoice_line_ids), 2),
            "prchrAcptcYn": "N",
            "remark": "credit note",
            "regrId": current_user.id,
            "regrNm": current_user.name,
            "modrId": current_user.id,
            "modrNm": current_user.name,
            "saleCtyCd": "1",
            "lpoNumber": lpo or None,
            "currencyTyCd": self.currency_id.name if self.currency_id.name else "ZMW",
            "exchangeRt": str(round(exchange_rate, 2)),
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
                    "dcAmt": round((line.quantity * self.calculate_tax_inclusive_price(line)) * (line.discount / 100),
                                   2),
                    "isrccCd": "",
                    "isrccNm": "",
                    "isrcRt": 0.0,
                    "isrcAmt": 0.0,
                    "vatCatCd": self.get_tax_description(line.tax_ids),
                    "exciseTxCatCd": None,
                    "vatTaxblAmt": round(line.price_subtotal, 2),
                    "exciseTaxblAmt": 0.0,
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "exciseTxAmt": 0.0,
                    "totAmt": round(line.price_total, 2),
                }
                for index, line in enumerate(self.invoice_line_ids)
            ]
        }

        payload_stock_items = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": self.partner_id.tpin or "1000000000",
            "custNm": self.partner_id.name if self.partner_id else None,
            "custBhfId": "000",
            "sarTyCd": "03",
            "ocrnDt": self.invoice_date.strftime('%Y%m%d') if self.invoice_date else None,
            "totItemCnt": len(self.invoice_line_ids),
            "totTaxblAmt": round(sum(line.price_subtotal for line in self.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in self.invoice_line_ids), 2),
            "totAmt": round(sum(line.price_total for line in self.invoice_line_ids), 2),
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
                    "vatCatCd": self.get_tax_description(line.tax_ids),
                    "iplCatCd": "IPL1",
                    "tlCatCd": "TL",
                    "exciseTxCatCd": "EXEEG",
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "iplAmt": 0.0,
                    "tlAmt": 0.0,
                    "exciseTxAmt": 0.0,
                    "taxAmt": round(line.price_total - line.price_subtotal, 2),
                    "totAmt": round(line.price_total, 2)
                } for index, line in enumerate(self.invoice_line_ids)
            ]
        }

        self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stock/saveStockItems', payload_stock_items,
                                "Save Stock Item API Response Endpoint")

        for line in self.invoice_line_ids:
            # Fetch the available quantity from the stock quant model
            available_quants = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id.usage', '=', 'internal')
            ])
            available_qty = sum(quant.quantity for quant in available_quants)

            remaining_qty = available_qty + line.quantity

        payload_stock_master = {
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
                } for line in self.invoice_line_ids
            ]
        }
        self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stockMaster/saveStockMaster', payload_stock_master,
                                "Stock Master Endpoint response")
        return payload

    def _post_to_api(self, url, payload, success_message_prefix):
        print('Sales Payload being sent:', json.dumps(payload, indent=4))
        _logger.info('Sending payload to API: %s', json.dumps(payload, indent=4))

        try:
            response = requests.post(url, json=payload)
            print(f'API responded with status code: {response.status_code}')
            _logger.info(f'API responded with status code: {response.status_code}')

            response.raise_for_status()  # This will raise an HTTPError if the status is 4xx or 5xx
            response_data = response.json()

            print('API response:', json.dumps(response_data, indent=4))
            _logger.info('API response: %s', json.dumps(response_data, indent=4))

            result_msg = response_data.get('resultMsg', 'No result message returned')
            data = response_data.get('data')

            if data:
                rcpt_no = data.get('rcptNo')
                intrl_data = data.get('intrlData')
                rcpt_sign = data.get('rcptSign')
                vsdc_rcpt_pbct_date = data.get('vsdcRcptPbctDate')
                sdc_id = data.get('sdcId')
                mrc_no = data.get('mrcNo')
                qr_code_url = data.get('qrCodeUrl')

                # Log the response data
                print(f'Response Data - rcpt_no: {rcpt_no}, intrl_data: {intrl_data}, rcpt_sign: {rcpt_sign}, '
                      f'vsdc_rcpt_pbct_date: {vsdc_rcpt_pbct_date}, sdc_id: {sdc_id}, mrc_no: {mrc_no}, '
                      f'qr_code_url: {qr_code_url}')
                _logger.info(f'Response Data - rcpt_no: {rcpt_no}, intrl_data: {intrl_data}, rcpt_sign: {rcpt_sign}, '
                             f'vsdc_rcpt_pbct_date: {vsdc_rcpt_pbct_date}, sdc_id: {sdc_id}, mrc_no: {mrc_no}, '
                             f'qr_code_url: {qr_code_url}')

                if self:
                    record = self[0]
                    record.message_post(body=f"{success_message_prefix}: {result_msg}")
                    _logger.info(f'{success_message_prefix}: {result_msg}')
                    print(f'{success_message_prefix}: {result_msg}: {result_msg} ')

                    record.write({
                        'rcpt_no': rcpt_no,
                        'intrl_data': intrl_data,
                        'rcpt_sign': rcpt_sign,
                        'vsdc_rcpt_pbct_date': vsdc_rcpt_pbct_date,
                        'sdc_id': sdc_id,
                        'mrc_no': mrc_no,
                        'qr_code_url': qr_code_url
                    })
                else:
                    _logger.warning('No records to post messages to')
                    print('No records to post messages to')

            else:
                _logger.error('No data returned in the response')
                print('No data returned in the response')

        except requests.exceptions.RequestException as e:
            _logger.error(f'API request failed: {str(e)}')
            print(f'API request failed: {str(e)}')
            # Handle additional error actions here if necessary

    def _post_to_stock_api(self, url, payload, success_message_prefix):

        print('Payload being sent:', json.dumps(payload, indent=4))
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            result_msg = response.json().get('resultMsg', 'No result message returned')
            if not self:
                _logger.warning('No records to post messages to')
                return
            for record in self:
                record.message_post(body=f"{success_message_prefix}: {result_msg}")
                _logger.info(f'{success_message_prefix}: {result_msg}')
                print(f'{success_message_prefix}: {result_msg}')
        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            if not self:
                _logger.error(f'API request failed: {error_msg} (No records to post messages to)')
                return
            for record in self:
                record.message_post(body=f"Error during API call: {error_msg}")
                _logger.error(f'API request failed: {error_msg}')
                print(f'API request failed: {error_msg}')

        # ==============================================================================================#
        #                                          DEBIT NOTE                                           #
        # ==============================================================================================#

    def get_debit_note_reason(self):
        reversal = self.env['account.debit.note'].search([('move_ids', 'in', self.id)])
        return reversal.reason if reversal else ''
        return None

    @api.model
    def _get_default_journal(self):  # Copy
        # Replace 'out_invoice' with the appropriate journal type if needed
        journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        return journal.id if journal else False

    def get_debit_receipt_no(self, ref):
        print(f"Fetching receipt number for invoice with reference: {ref}")

        # Find the original invoice based on the reference
        original_invoice = self.env['account.move'].search([('name', '=', ref), ('move_type', '!=', 'in_refund')],
                                                           limit=1)

        if original_invoice:
            print(f"Original invoice found: {original_invoice.id}")
            if hasattr(original_invoice, 'rcpt_no'):
                if original_invoice.rcpt_no:
                    print(f"Receipt number found: {original_invoice.rcpt_no}")
                    return original_invoice.rcpt_no
                else:
                    print("Receipt number is empty.")
            else:
                _logger.warning("Original invoice does not have rcpt_no attribute.")
        else:
            _logger.warning(f"Original invoice not found for reference: {ref}")

        return None

    def get_receipt_no_by_invoice_number(self, invoice_number):
        print(f"Searching for receipt number with invoice number: {invoice_number}")

        # Search for the move with the given invoice number
        invoice = self.search([('ref', '=', invoice_number)], limit=1)

        if not invoice:
            print(f"No invoice found with number: {invoice_number}")
            return None

        print(f"Invoice found: {invoice.id}")

        # Check if the invoice is a sale or credit note
        if invoice.move_type in ['in_refund']:
            if hasattr(invoice, 'rcpt_no'):
                print(f"Receipt number found: {invoice.rcpt_no}")
                return invoice.rcpt_no
            else:
                print(f"Invoice does not have 'rcpt_no' field.")
                return None
        else:
            print(f"Invoice {invoice.id} is neither a sale nor a credit note.")
            return None

    def debit_note_payload(self, original_ref):
        current_user = self.env.user
        company = self.env.company
        # tpin = self.partner_id.tpin if self.partner_id else None
        tpin, lpo, export_country_code = self.get_sales_order_fields()
        print(f"Original Reference in debit_note_payload: {original_ref}")

        debit_move = self.env['account.move'].browse(self._context.get('active_id'))
        partner = debit_move.partner_id
        debit_note_reason = self.get_debit_note_reason()
        rcpt_no = self.get_debit_receipt_no(original_ref)
        print(f"Receipt Number: {rcpt_no}")

        debit_reversal_id = self._context.get('active_id')
        debit_reversal_move = self.env['account.debit.note'].browse(debit_reversal_id)
        debit_note_reason = debit_reversal_move.reason if debit_reversal_move else "01"
        print(f'Fetched Reversal Reason: {debit_note_reason}')

        # Fetch the related sale order to get the LPO and export country code
        sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
        lpo = sale_order.lpo if sale_order else None
        export_country_code = sale_order.export_country_id.code if sale_order and sale_order.export_country_id else None
        exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgSdcId": company.org_sdc_id,
            "orgInvcNo": rcpt_no,
            "cisInvcNo": self.name,
            "custTpin": tpin or '1000000000',

            "custNm": self.partner_id.name,
            "salesTyCd": "N",
            "rcptTyCd": "D",
            "pmtTyCd": "01",
            "salesSttsCd": "02",
            "cfmDt": self.invoice_date.strftime('%Y%m%d%H%M%S') if self.invoice_date else None,
            "salesDt": datetime.now().strftime('%Y%m%d'),
            "stockRlsDt": None,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": None,
            "rfdRsnCd": None,
            "totItemCnt": len(self.invoice_line_ids),
            "taxblAmtA": self.calculate_taxable_amount(self.invoice_line_ids, 'A'),
            "taxblAmtB": self.calculate_taxable_amount(self.invoice_line_ids, 'B'),
            "taxblAmtC": self.calculate_taxable_amount(self.invoice_line_ids, 'C'),
            "taxblAmtC1": self.calculate_taxable_amount(self.invoice_line_ids, 'C1'),
            "taxblAmtC2": self.calculate_taxable_amount(self.invoice_line_ids, 'C2'),
            "taxblAmtC3": self.calculate_taxable_amount(self.invoice_line_ids, 'C3'),
            "taxblAmtD": self.calculate_taxable_amount(self.invoice_line_ids, 'D'),
            "taxblAmtRvat": self.calculate_taxable_amount(self.invoice_line_ids, 'Rvat'),
            "taxblAmtE": self.calculate_taxable_amount(self.invoice_line_ids, 'E'),
            "taxblAmtF": self.calculate_taxable_amount(self.invoice_line_ids, 'F'),
            "taxblAmtIpl1": self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl1'),
            "taxblAmtIpl2": self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl2'),
            "taxblAmtTl": self.calculate_taxable_amount(self.invoice_line_ids, 'Tl'),
            "taxblAmtEcm": self.calculate_taxable_amount(self.invoice_line_ids, 'Ecm'),
            "taxblAmtExeeg": self.calculate_taxable_amount(self.invoice_line_ids, 'Exeeg'),
            "taxblAmtTot": self.calculate_taxable_amount(self.invoice_line_ids, 'Tot'),
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
            "taxAmtA": self.calculate_tax_amount(self.invoice_line_ids, 'A'),
            "taxAmtB": self.calculate_tax_amount(self.invoice_line_ids, 'B'),
            "taxAmtC": self.calculate_tax_amount(self.invoice_line_ids, 'C'),
            "taxAmtC1": self.calculate_tax_amount(self.invoice_line_ids, 'C1'),
            "taxAmtC2": self.calculate_tax_amount(self.invoice_line_ids, 'C2'),
            "taxAmtC3": self.calculate_tax_amount(self.invoice_line_ids, 'C3'),
            "taxAmtD": self.calculate_tax_amount(self.invoice_line_ids, 'D'),
            "taxAmtRvat": self.calculate_tax_amount(self.invoice_line_ids, 'Rvat'),
            "taxAmtE": self.calculate_tax_amount(self.invoice_line_ids, 'E'),
            "taxAmtF": self.calculate_tax_amount(self.invoice_line_ids, 'F'),
            "taxAmtIpl1": self.calculate_tax_amount(self.invoice_line_ids, 'Ipl1'),
            "taxAmtIpl2": self.calculate_tax_amount(self.invoice_line_ids, 'Ipl2'),
            "taxAmtTl": self.calculate_tax_amount(self.invoice_line_ids, 'Tl'),
            "taxAmtEcm": self.calculate_tax_amount(self.invoice_line_ids, 'Ecm'),
            "taxAmtExeeg": self.calculate_tax_amount(self.invoice_line_ids, 'Exeeg'),
            "taxAmtTot": self.calculate_tax_amount(self.invoice_line_ids, 'Tot'),
            "totTaxblAmt": round(sum(line.price_subtotal for line in self.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in self.invoice_line_ids), 2),
            "totAmt": round(sum(line.price_total for line in self.invoice_line_ids), 2),
            "prchrAcptcYn": "N",
            "remark": "Debit note",
            "regrId": current_user.id,
            "regrNm": current_user.name,
            "modrId": current_user.id,
            "modrNm": current_user.name,
            "saleCtyCd": "1",
            "lpoNumber": lpo or None,
            "currencyTyCd": self.currency_id.name if self.currency_id else "ZMW",
            "exchangeRt": str(round(exchange_rate, 2)),
            "destnCountryCd": export_country_code or "ZM",
            "dbtRsnCd": debit_note_reason or "02",
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
                    "qty": line.quantity,
                    "prc": round(self.calculate_tax_inclusive_price(line), 2),
                    "splyAmt": round(line.quantity * self.calculate_tax_inclusive_price(line), 2),
                    "dcRt": line.discount,
                    "dcAmt": round((line.quantity * self.calculate_tax_inclusive_price(line)) * (line.discount / 100),
                                   2),
                    "isrccCd": "",
                    "isrccNm": "",
                    "isrcRt": 0.0,
                    "isrcAmt": 0.0,
                    "vatCatCd": self.get_tax_description(line.tax_ids),
                    "exciseTxCatCd": None,
                    "vatTaxblAmt": round(line.price_subtotal, 2),
                    "exciseTaxblAmt": 0.0,
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "exciseTxAmt": 0.0,
                    "totAmt": round(line.price_total, 2),
                } for index, line in enumerate(self.invoice_line_ids)
            ]
        }
        payload_stock_endpoint = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": self.partner_id.tpin if self.partner_id else None,
            "custNm": self.partner_id.name if self.partner_id else None,
            "custBhfId": "000",
            "sarTyCd": "12",
            "ocrnDt": self.invoice_date.strftime('%Y%m%d') if self.invoice_date else None,
            "totItemCnt": len(self.invoice_line_ids),
            "totTaxblAmt": round(sum(line.price_subtotal for line in self.invoice_line_ids), 2),
            "totTaxAmt": round(sum(line.price_total - line.price_subtotal for line in self.invoice_line_ids), 2),
            "totAmt": round(sum(line.price_total for line in self.invoice_line_ids), 2),
            "remark": 'debit Note',
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
                    "vatCatCd": self.get_tax_description(line.tax_ids),
                    "iplCatCd": "IPL1",
                    "tlCatCd": "TL",
                    "exciseTxCatCd": "EXEEG",
                    "vatAmt": round(line.price_total - line.price_subtotal, 2),
                    "iplAmt": 0.0,
                    "tlAmt": 0.0,
                    "exciseTxAmt": 0.0,
                    "taxAmt": round(line.price_total - line.price_subtotal, 2),
                    "totAmt": round(line.price_total, 2)
                }
                for index, line in enumerate(self.invoice_line_ids)
            ]
        }
        self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stock/saveStockItems', payload_stock_endpoint,
                                "Save Stock Item API Response Endpoint")
        for line in self.invoice_line_ids:
            # Fetch the available quantity from the stock quant model
            available_quants = self.env['stock.quant'].search([
                ('product_id', '=', line.product_id.id),
                ('location_id.usage', '=', 'internal')
            ])
            available_qty = sum(quant.quantity for quant in available_quants)
            remaining_qty = available_qty - line.quantity
        payload_stock_master = {
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
                } for line in self.invoice_line_ids
            ]
        }
        self._post_to_stock_api('http://vsdc.iswe.co.zm/sandbox/stockMaster/saveStockMaster', payload_stock_master,
                                "Stock Master Endpoint response")
        return payload


class AccountDebitNoteWizard(models.TransientModel):
    _inherit = 'account.debit.note'
    reason = fields.Selection([
        ('01', 'Wrong quantity invoiced'),
        ('02', 'Wrong invoice amount'),
        ('03', 'Omitted item'),
        ('04', 'Other [specify]'),
    ], string='Reason', required=True)
    date = fields.Date('Debit Note Date', required=True, default=fields.Date.context_today)
    copy_lines = fields.Boolean('Copy Lines', default=True)
    journal_id = fields.Many2one('account.journal', 'Journal', required=True,
                                 default=lambda self: self._get_default_journal())
    move_type = fields.Selection([
        ('out_invoice', 'Customer Invoice'),
        ('in_invoice', 'Vendor Bill'),
        ('out_refund', 'Customer Credit Note'),
        ('in_refund', 'Vendor Credit Note'),
        ('out_debit', 'Customer Debit Note'),
        ('in_debit', 'Vendor Debit Note'),
    ], string='Type', required=True, default='in_refund')
    journal_type = fields.Selection(related='journal_id.type', string='Journal Type', store=True)
    # move_ids = fields.Many2many('account.move', string='Invoices')
    move_ids = fields.Many2many('account.move', 'account_debit_note_move_rel', 'note_id', 'move_id', string='Moves')
    copy_lines = fields.Boolean(string='Copy Lines', default='True')

    @api.model
    def _get_default_journal(self):  # Copy
        # Replace 'out_invoice' with the appropriate journal type if needed
        journal = self.env['account.journal'].search(['|', ('type', '=', 'sale'), ('type', '=', 'purchase')],
                                                     limit=1)
        return journal.id if journal else False

    def create_debit(self):
        self.ensure_one()
        new_moves = self.env['account.move']

        for move in self.move_ids.with_context(include_business_fields=True):  # Copy sale/purchase links
            partner = move.partner_id
            account_id = self.env['account.account'].search([('deprecated', '=', False)], limit=1).id
            if not account_id:
                raise ValidationError("No account found to use for the debit note lines.")

            debit_note_vals = {
                'move_type': 'in_refund',
                'partner_id': partner.id,
                'invoice_date': fields.Date.context_today(self),
                'ref': move.name,
                'invoice_line_ids': [(0, 0, {
                    'product_id': line.product_id.id,
                    'quantity': line.quantity,
                    'price_unit': line.price_unit,
                    'account_id': account_id,
                    'tax_ids': [(6, 0, line.tax_ids.ids)]
                }) for line in move.invoice_line_ids],
            }

            new_move = self.env['account.move'].create(debit_note_vals)
            move_msg = _("This debit note was created from: %s", move._get_html_link())
            new_move.message_post(body=move_msg)
            new_moves |= new_move

            self._process_moves(new_move)

        action = {
            'name': _('Debit Notes'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'context': {'default_move_type': 'in_refund'},
        }
        if len(new_moves) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': new_moves.id,
            })
        else:
            action.update({
                'view_mode': 'tree,form',
                'domain': [('id', 'in', new_moves.ids)],
            })
        return action

    def _process_moves(self, debit_note):
        debit_note.write({'state': 'draft'})


class AccountMoveSend(models.TransientModel):
    _inherit = 'account.move.send'

    def action_send_and_print(self, **kwargs):
        # Call the super method and pass any keyword arguments
        res = super(AccountMoveSend, self).action_send_and_print(**kwargs)

        # Update the is_printed field for the printed invoices
        for move in self.move_ids:
            if not move.is_printed:
                move.is_printed = True
                move.message_post(body="This document has been printed and marked as 'Copy' for future prints.")
        return res
