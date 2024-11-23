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
import pytz

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_type = fields.Char('Sale Type Code', default='N')
    receipt_type = fields.Char('Receipt Type Code', default='S')
    # payment_type = fields.Char('Payment Type Code')
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

    def create(self, vals):
        """ Override create to set the values from sale order if they exist """
        # Check for sales order reference in vals
        if 'invoice_origin' in vals:
            sale_order = self.env['sale.order'].search([('name', '=', vals['invoice_origin'])], limit=1)
            if sale_order:
                vals['tpin'] = sale_order.tpin or ''
                vals['lpo'] = sale_order.lpo or ''
                vals['export_country_id'] = sale_order.export_country_id.id or False

        # Create the account move
        move = super(AccountMove, self).create(vals)
        return move

    def send_to_external_api(self, order_payload):
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)

        sales_url = config_settings.sales_endpoint
        stock_url = config_settings.stock_io_endpoint
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
    custom_payment_type = fields.Selection([
        ('01', 'CASH'),
        ('02', 'CREDIT'),
        ('03', 'CASH/CREDIT'),
        ('04', 'BANK CHECK'),
        ('05', 'DEBIT&CREDIT CARD'),
        ('06', 'MOBILE MONEY'),
        ('07', 'BANK TRANSFER'),
        ('08', 'OTHER'),
    ], string='Payment Method', required=False, default="01")

    @api.depends('reversal_reason', 'debit_note_reason', 'custom_payment_type')
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

        custom_payment_type_dict = dict([
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
            record.custom_payment_type_text = custom_payment_type_dict.get(record.custom_payment_type, "")

    reversal_reason_text = fields.Char(string='Reversal Reason Text', compute='_compute_reason_text')
    debit_note_reason_text = fields.Char(string='Debit Note Reason Text', compute='_compute_reason_text')
    custom_payment_type_text = fields.Char(string='Payment Type', compute='_compute_reason_text')

    @api.constrains('tpin')
    def _check_tpin(self):
        for record in self:
            if record.tpin and not record.tpin.isdigit():
                raise ValidationError('TPIN must contain only numbers.')
            if record.tpin and len(record.tpin) > 10:
                raise ValidationError('TPIN must be at most 10 digits.')

    @api.onchange('partner_id')
    def _change_partner_id(self):
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

    def get_tax_description(self, taxes):
        if taxes:
            return ", ".join(tax.description or "" for tax in taxes)
        return ""
    
    def get_tax_rate(self, tax):
        return tax.amount if tax else 0.0


    # def calculate_taxable_amount(self, lines, tax_category):
    #     total_amount = 0.0
    #     for line in lines:
    #         tax_description = self.get_tax_description(line.tax_ids)
    #         if tax_category in tax_description:
    #             tax_rate = sum(line.tax_ids.mapped('amount')) / 100
    #             # Calculate discounted price with tax removed
    #             line_price_incl_tax = line.price_unit * (1 + tax_rate)
    #             discounted_price = line_price_incl_tax * (1 - (line.discount / 100))
    #             taxable_amount = round((line.quantity * discounted_price) / (1 + tax_rate), 4)
    #             total_amount += taxable_amount
    #     return total_amount

    def calculate_taxable_amount(self, lines, tax_category):
        total_amount = 0.0
        for line in lines:
            tax_description = self.get_tax_description(line.tax_ids)
            if tax_category in tax_description:
                tax_rate = sum(line.tax_ids.mapped('amount')) / 100
                # Calculate discounted price with tax removed
                # line_price_excl_tax = line.price_unit
                # discounted_price = round((line_price_excl_tax) * (1 - (line.discount / 100)), 2)
                # taxable_amount = round((round(line.quantity, 2) * discounted_price) / (1 + tax_rate), 4)
                
                item_sply_amount = (line.quantity) * (line.price_unit)
                item_discount_amount = ((item_sply_amount) * (line.discount / 100))
                item_net_sply_amount = (item_sply_amount) - (round(item_discount_amount, 2))
                taxable_amount_custom = round(item_net_sply_amount / (1 + tax_rate) , 4)
                total_amount += taxable_amount_custom
        return total_amount

    def calculate_tax_amount(self, lines, tax_category):
        total_tax = 0.0
        for line in lines:
            tax_description = self.get_tax_description(line.tax_ids)
            if tax_category in tax_description:
                tax_rate = sum(line.tax_ids.mapped('amount')) / 100
                # Calculate the taxable amount without tax
                # line_price_excl_tax = line.price_unit
                # discounted_price = round((line_price_excl_tax) * (1 - (line.discount / 100)), 2)
                # taxable_amount = round((round(line.quantity, 2) * discounted_price) / (1 + tax_rate), 4)
                # tax_amount = round(taxable_amount * tax_rate, 4)
                
                item_sply_amount = (line.quantity) * (line.price_unit)
                item_discount_amount = ((item_sply_amount) * (line.discount / 100))
                item_net_sply_amount = (item_sply_amount) - (round(item_discount_amount, 2))
                taxable_amount_custom = round(item_net_sply_amount / (1 + tax_rate) * tax_rate, 4)
                
                total_tax += taxable_amount_custom
        return total_tax

    # def calculate_tax_amount(self, lines, tax_category):
    #     total_tax = 0.0
    #     for line in lines:
    #         tax_description = self.get_tax_description(line.tax_ids)
    #         if tax_category in tax_description:
    #             tax_rate = sum(line.tax_ids.mapped('amount')) / 100
    #             # Calculate the taxable amount without tax
    #             line_price_incl_tax = line.price_unit * (1 + tax_rate)
    #             discounted_price = line_price_incl_tax * (1 - (line.discount / 100))
    #             taxable_amount = round((line.quantity * discounted_price) / (1 + tax_rate), 4)
    #             tax_amount = round(taxable_amount * tax_rate, 4)
    #             total_tax += tax_amount
    #     return total_tax

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
        if self.move_type in ['out_refund', 'in_refund']:
            # Prevent automatic reconciliation for credit notes
            self.line_ids.remove_move_reconcile()

        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)

        # Check for stockable products only
        _logger.info(f" =====================invoice_line_ids===================== {self.invoice_line_ids}")
        stockable_product_lines = self.invoice_line_ids.filtered(lambda l: l.product_id.detailed_type == 'product')

        if self.move_type in ['out_invoice', 'out_refund', 'in_refund']:
            # Check for missing taxes
            for line in self.invoice_line_ids:
                if not line.tax_ids:
                    raise UserError("Please set taxes on all invoice lines before confirming the invoice.")

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

            # Always post the sales payload, even if no stockable products
            if self.move_type == 'out_invoice':
                payload = self.generate_sales_payload()  # Sales payload for all products (including services)
                self._post_to_api(config_settings.sales_endpoint, payload, "Save Sales API Response resultMsg")

            # Only handle stock-related operations for stockable products
            if stockable_product_lines:
                # Process stockable products for stock APIs
                if self.move_type == 'out_invoice':
                    payload_stock_items = self.generate_stock_payload_items(stockable_product_lines, '11', 'Normal Sale')
                    self._post_to_stock_api(config_settings.stock_io_endpoint, payload_stock_items,
                                            "Save Stock Item API Response")

                    payload_stock_master = self.generate_stock_payload_master(stockable_product_lines)
                    self._post_to_stock_api(config_settings.stock_master_endpoint, payload_stock_master,
                                            "Stock Master API Response")

                elif self.move_type == 'out_refund':
                    if not self._is_internet_connected():
                        raise UserError("Cannot perform credit note offline. Please check your internet connection.")

                    payload = self.credit_note_payload()
                    self._post_to_api(config_settings.sales_endpoint, payload,
                                    "Save Credit Note API Response resultMsg")

                    reversal_id = self._context.get('active_id')
                    reversal_move = self.env['account.move.reversal'].browse(reversal_id)
                    reversal_reason = reversal_move.reason if reversal_move else "01"
                    self.write({'reversal_reason': reversal_reason})

                    # Only if there are stockable products
                    payload_stock_items = self.generate_stock_payload_items(stockable_product_lines, '03', 'Credit Note')
                    self._post_to_stock_api(config_settings.stock_io_endpoint, payload_stock_items,
                                            "Save Stock Item API Response")

                    payload_stock_master = self.generate_stock_payload_master(stockable_product_lines)
                    self._post_to_stock_api(config_settings.stock_master_endpoint, payload_stock_master,
                                            "Stock Master API Response")

                elif self.move_type == 'in_refund':
                    original_ref = self.ref
                    payload = self.debit_note_payload(original_ref)
                    self._post_to_api(config_settings.sales_endpoint, payload, "Save Debit Note API Response resultMsg")

                    debit_reversal_id = self._context.get('active_id')
                    debit_reversal_move = self.env['account.debit.note'].browse(debit_reversal_id)
                    debit_note_reason = debit_reversal_move.reason if debit_reversal_move else "01"
                    self.write({'debit_note_reason': debit_note_reason})

                    payload_stock_items = self.generate_stock_payload_items(stockable_product_lines, '12' , 'Debit Note')
                    self._post_to_stock_api(config_settings.stock_io_endpoint, payload_stock_items,
                                            "Save Stock Item API Response")

                    payload_stock_master = self.generate_stock_payload_master(stockable_product_lines)
                    self._post_to_stock_api(config_settings.stock_master_endpoint, payload_stock_master,
                                            "Stock Master API Response")

            # Handle stock operations for stockable products only
            for invoice in self:
                if stockable_product_lines:
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
                        self._accounting_update_stock_quantities(invoice, stockable_product_lines)

                    if invoice.move_type == 'out_refund':
                        self._update_stock_quantities(invoice, stockable_product_lines)

                    if invoice.move_type == 'in_refund':
                        self._debit_update_stock_quantities(invoice, stockable_product_lines)

            self.generate_qr_code_button()

        return res

    def _is_internet_connected(self):
        try:
            # Try to connect to a reliable public host
            socket.create_connection(("8.8.8.8", 53))
            return True
        except OSError:
            return False

    def _accounting_update_stock_quantities(self, invoice, stockable_product_lines):
        # Process only stockable product lines
        for line in stockable_product_lines:
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

    def _update_stock_quantities(self, invoice, stockable_product_lines):
        for line in stockable_product_lines:
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

    def _debit_update_stock_quantities(self, invoice, stockable_product_lines):
        for line in stockable_product_lines:
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

    def _generate_item(self, index, line):
        tax_rate = sum(line.tax_ids.mapped('amount')) / 100
        item_price_with_tax_incl = line.price_unit * (1 + tax_rate)
        # item_sply_amount_incl = line.quantity * round(item_price_with_tax, 4)
        item_sply_amount = (line.quantity) * (line.price_unit)
        item_discount_amount = ((item_sply_amount) * (line.discount / 100))
        item_net_sply_amount = (item_sply_amount) - (round(item_discount_amount, 2))
        vat_taxbleAmt = item_net_sply_amount / (1 + tax_rate)
        vat_Amt = vat_taxbleAmt * tax_rate
        tot_Amt = item_net_sply_amount

        return {
            "itemSeq": index + 1,
            "itemCd": line.product_id.product_tmpl_id.item_Cd,
            "itemClsCd": line.product_id.product_tmpl_id.item_cls_cd,
            "itemNm": line.product_id.name,
            "bcd": line.product_id.barcode,
            "pkgUnitCd": line.product_id.product_tmpl_id.packaging_unit_cd,
            "pkg": line.quantity,
            "qtyUnitCd": line.product_id.product_tmpl_id.quantity_unit_cd,
            "qty": round(line.quantity, 4),
            "itemExprDt": None,
            "prc": round(line.price_unit, 4),
            "splyAmt": round(item_sply_amount, 4),
            "dcRt": line.discount,
            "dcAmt": round(item_discount_amount, 2),
            "isrccCd": "",
            "isrccNm": "",
            "isrcRt": 0.0,
            "isrcAmt": 0.0,
            "totDcAmt": round(item_discount_amount, 2),
            "vatCatCd": self.get_tax_description(line.tax_ids),
            "exciseTxCatCd": None,
            "vatAmt": round(vat_Amt, 4),
            "taxblAmt": round(vat_taxbleAmt, 4),
            "iplAmt": 0.0,
            "tlAmt": 0.0,
            "exciseTaxblAmt": 0.0,
            "vatTaxblAmt": round(vat_taxbleAmt, 4),
            "exciseTxAmt": 0.0,
            "taxAmt": round(vat_Amt, 4),
            "totAmt": round(tot_Amt, 4), 
        }

    def generate_sales_payload(self):
        current_user = self.env.user
        company = self.env.company
        tpin, lpo, export_country_code = self.get_sales_order_fields()
        tpin = self.tpin
        lpo = self.lpo
        local_tz = pytz.timezone("Africa/Lusaka")  # e.g., 'America/New_York'
        now = datetime.now(local_tz)
        date_prefix = now.strftime('%Y/%m/%d/%H:%M:%S')  # Formats as YYYY/mm/dd/HH:MM:SS
        sequence_number = self.env['ir.sequence'].next_by_code('account.move')  # Generates the next sequence number
        if self.name.startswith('INV/') and '/' in self.name:
            sequence_number = self.name.split('/')[-1]  # Get the last part, which is the numeric sequence
        cisInvcNo_value = f'INV/{date_prefix}/{sequence_number}'
        exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)
        tax_rates = [(sum(line.tax_ids.mapped('amount')) / 100) for line in self.invoice_line_ids]
        
        # Get tpin value
        customer = self.partner_id
        custTpin = (
            tpin or  # Use tpin from the current record
            (customer.vat) or  # Use tax_id from customer
            "1000000000"  # Default fallback value
        )

        item_list = []
        for index, line in enumerate(self.invoice_line_ids):    
            item = self._generate_item(index, line)
            item_list.append(item)

        # Summary amounts
        totTaxblAmt = sum(item['vatTaxblAmt'] for item in item_list)
        totTaxAmt = sum(item['vatAmt'] for item in item_list)
        totAmt = sum(item['totAmt'] for item in item_list)

        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgInvcNo": 0,
            "cisInvcNo": cisInvcNo_value,
            "custTpin": custTpin,
            "custNm": self.partner_id.name,
            "salesTyCd": self.sale_type or 'N',
            "rcptTyCd": self.receipt_type or 'S',
            "pmtTyCd": self.custom_payment_type,
            "salesSttsCd": self.sales_status or '02',
            "cfmDt": self.invoice_date.strftime('%Y%m%d%H%M%S') if self.invoice_date else None,
            "salesDt": datetime.now().strftime('%Y%m%d'),
            "stockRlsDt": None,
            "cnclReqDt": None,
            "cnclDt": None,
            "rfdDt": None,
            "rfdRsnCd": "",
            "totItemCnt": len(self.invoice_line_ids),
            "taxblAmtA": round(self.calculate_taxable_amount(self.invoice_line_ids, 'A'), 4),
            "taxblAmtB": round(self.calculate_taxable_amount(self.invoice_line_ids, 'B'), 4),
            "taxblAmtC": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C'), 4),
            "taxblAmtC1": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C1'), 4),
            "taxblAmtC2": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C2'), 4),
            "taxblAmtC3": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C3'), 4),
            "taxblAmtD": round(self.calculate_taxable_amount(self.invoice_line_ids, 'D'), 4),
            "taxblAmtRvat": round(self.calculate_taxable_amount(self.invoice_line_ids, 'RVAT'), 4),
            "taxblAmtE": round(self.calculate_taxable_amount(self.invoice_line_ids, 'E'), 4),
            "taxblAmtF": round(self.calculate_taxable_amount(self.invoice_line_ids, 'F'), 4),
            "taxblAmtIpl1": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl1'), 4),
            "taxblAmtIpl2": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl2'), 4),
            "taxblAmtTl": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Tl'), 4),
            "taxblAmtEcm": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ecm'), 4),
            "taxblAmtExeeg": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Exeeg'), 4),
            "taxblAmtTot": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Tot'), 4),
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
            "taxAmtA": round(self.calculate_tax_amount(self.invoice_line_ids, 'A'), 4),
            "taxAmtB": round(self.calculate_tax_amount(self.invoice_line_ids, 'B'), 4),
            "taxAmtC": round(self.calculate_tax_amount(self.invoice_line_ids, 'C'), 4),
            "taxAmtC1": round(self.calculate_tax_amount(self.invoice_line_ids, 'C1'), 4),
            "taxAmtC2": round(self.calculate_tax_amount(self.invoice_line_ids, 'C2'), 4),
            "taxAmtC3": round(self.calculate_tax_amount(self.invoice_line_ids, 'C3'), 4),
            "taxAmtD": round(self.calculate_tax_amount(self.invoice_line_ids, 'D'), 4),
            "taxAmtRvat": round(self.calculate_tax_amount(self.invoice_line_ids, 'Rvat'), 4),
            "taxAmtE": round(self.calculate_tax_amount(self.invoice_line_ids, 'E'), 4),
            "taxAmtF": round(self.calculate_tax_amount(self.invoice_line_ids, 'F'), 4),
            "taxAmtIpl1": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ipl1'), 4),
            "taxAmtIpl2": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ipl2'), 4),
            "taxAmtTl": round(self.calculate_tax_amount(self.invoice_line_ids, 'Tl'), 4),
            "taxAmtEcm": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ecm'), 4),
            "taxAmtExeeg": round(self.calculate_tax_amount(self.invoice_line_ids, 'Exeeg'), 4),
            "taxAmtTot": round(self.calculate_tax_amount(self.invoice_line_ids, 'Tot'), 4),
            "totTaxblAmt": round(totTaxblAmt, 4),
            "totTaxAmt": round(totTaxAmt, 4),
            "totAmt": round(totAmt, 4),
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
            "destnCountryCd": export_country_code,
            "dbtRsnCd": "",
            "invcAdjustReason": "",
            "itemList": item_list
        }

        return payload

    def generate_stock_payload_items(self, stockable_product_lines, sartyCd , remark):
        tpin, lpo, export_country_code = self.get_sales_order_fields()
        current_user = self.env.user
        company = self.env.company
        customer = self.partner_id
        custTpin = (
                tpin or  # Use tpin from the current record
                (customer.vat) or  # Use tax_id from customer
                "1000000000"  # Default fallback value
        )

        item_list = []
        for index, line in enumerate(stockable_product_lines):
            item = self._generate_item(index, line)
            item_list.append(item)
        
        totTaxblAmt = sum(item['vatTaxblAmt'] for item in item_list)
        totTaxAmt = sum(item['vatAmt'] for item in item_list)
        totAmt = sum(item['totAmt'] for item in item_list)

        payload_stock_items = {
        "tpin": company.tpin,
        "bhfId": company.bhf_id,
        "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
        "orgSarNo": 0,
        "regTyCd": "M",
        "custTpin": custTpin,
        "custNm": self.partner_id.name,
        "custBhfId": "000",
        "sarTyCd": sartyCd,
        "ocrnDt": self.invoice_date.strftime('%Y%m%d') if self.invoice_date else None,
        "totItemCnt": len(stockable_product_lines),  # Count only stockable product lines
        "totTaxblAmt": round(totTaxblAmt, 4),
        "totTaxAmt": round(totTaxAmt, 4),
        "totAmt": round(totAmt, 4),
        "remark": remark,
        "regrId": current_user.name,
        "regrNm": current_user.id,
        "modrNm": current_user.name,
        "modrId": current_user.id,
        "itemList": item_list
        }
        return payload_stock_items

    def generate_stock_payload_master(self, stockable_product_lines):
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
                    "itemCd": line.product_id.product_tmpl_id.item_Cd,
                    # Calculate available_qty and remaining_qty for each item
                    "rsdQty": sum(quant.quantity for quant in self.env['stock.quant'].search([
                        ('product_id', '=', line.product_id.id),
                        ('location_id.usage', '=', 'internal')
                    ])) - line.quantity
                } for index, line in enumerate(stockable_product_lines)
            ]
        }
        return payload_stock_master

    # =============================================================================================#
    #                                          CREDIT NOTE                                         #
    # =============================================================================================#
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
        tpin, lpo, export_country_code = self.get_sales_order_fields()
        rcpt_no = self.get_receipt_no(self)
        print(rcpt_no)
        local_tz = pytz.timezone("Africa/Lusaka")  # e.g., 'America/New_York'
        now = datetime.now(local_tz)
        date_prefix = now.strftime('%Y/%m/%d/%H:%M:%S')  # Formats as YYYY/mm/dd/HH:MM:SS
        sequence_number = self.env['ir.sequence'].next_by_code('account.move')  # Generates the next sequence number
        if self.name.startswith('INV/') and '/' in self.name:
            sequence_number = self.name.split('/')[-1]  # Get the last part, which is the numeric sequence
        cisInvcNo_value = f'INV/{date_prefix}/{sequence_number}'
        credit_move = self.env['account.move'].browse(self._context.get('active_id'))
        print('Credit Id', credit_move)
        reversal_id = self._context.get('active_id')
        reversal_move = self.env['account.move.reversal'].browse(reversal_id)
        reversal_reason = reversal_move.reason if reversal_move else "01"
        print(f'Fetched Reversal Reason: {reversal_reason}')
        sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
        lpo = sale_order.lpo if sale_order else None
        export_country_code = sale_order.export_country_id.code if sale_order and sale_order.export_country_id else None
        exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)
        customer = self.partner_id
        custTpin = (
                tpin or  # Use tpin from the current record
                (customer.vat) or  # Use tax_id from customer
                "1000000000"  # Default fallback value
        )

        item_list = []
        for index, line in enumerate(self.invoice_line_ids):
            tax_rate = sum(line.tax_ids.mapped('amount')) / 100
            item_price_with_tax_incl = line.price_unit * (1 + tax_rate)
            # item_sply_amount_incl = line.quantity * round(item_price_with_tax, 4)
            item_sply_amount = (line.quantity) * (line.price_unit)
            item_discount_amount = ((item_sply_amount) * (line.discount / 100))
            item_net_sply_amount = (item_sply_amount) - (round(item_discount_amount, 2))
            vat_taxbleAmt = item_net_sply_amount / (1 + tax_rate)
            vat_Amt = vat_taxbleAmt * tax_rate
            tot_Amt = item_net_sply_amount

            item_list.append({
                "itemSeq": index + 1,
                "itemCd": line.product_id.product_tmpl_id.item_Cd,
                "itemClsCd": line.product_id.product_tmpl_id.item_cls_cd,
                "itemNm": line.product_id.name,
                "bcd": line.product_id.barcode,
                "pkgUnitCd": line.product_id.product_tmpl_id.packaging_unit_cd,
                "pkg": line.quantity,
                "qtyUnitCd": line.product_id.product_tmpl_id.quantity_unit_cd,
                "qty": round(line.quantity, 4),
                "prc": round(line.price_unit, 4),
                "splyAmt": round(item_sply_amount, 4),
                "dcRt": line.discount,
                "dcAmt": round(item_discount_amount, 2),
                "isrccCd": "",
                "isrccNm": "",
                "isrcRt": 0.0,
                "isrcAmt": 0.0,
                "vatCatCd": self.get_tax_description(line.tax_ids),
                "exciseTxCatCd": None,
                "vatTaxblAmt": round(vat_taxbleAmt, 4),
                "exciseTaxblAmt": 0.0,
                "vatAmt": round(vat_Amt, 4),
                "exciseTxAmt": 0.0,
                "totAmt": round(tot_Amt, 4),
            })

        # Summary amounts
        totTaxblAmt = sum(item['vatTaxblAmt'] for item in item_list)
        totTaxAmt = sum(item['vatAmt'] for item in item_list)
        totAmt = sum(item['totAmt'] for item in item_list)

        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgSdcId": company.org_sdc_id,
            "orgInvcNo": rcpt_no,
            "cisInvcNo": cisInvcNo_value,
            "custTpin": custTpin,
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
            "taxblAmtA": round(self.calculate_taxable_amount(self.invoice_line_ids, 'A'), 4),
            "taxblAmtB": round(self.calculate_taxable_amount(self.invoice_line_ids, 'B'), 4),
            "taxblAmtC": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C'), 4),
            "taxblAmtC1": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C1'), 4),
            "taxblAmtC2": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C2'), 4),
            "taxblAmtC3": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C3'), 4),
            "taxblAmtD": round(self.calculate_taxable_amount(self.invoice_line_ids, 'D'), 4),
            "taxblAmtRvat": round(self.calculate_taxable_amount(self.invoice_line_ids, 'RVAT'), 4),
            "taxblAmtE": round(self.calculate_taxable_amount(self.invoice_line_ids, 'E'), 4),
            "taxblAmtF": round(self.calculate_taxable_amount(self.invoice_line_ids, 'F'), 4),
            "taxblAmtIpl1": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl1'), 4),
            "taxblAmtIpl2": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl2'), 4),
            "taxblAmtTl": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Tl'), 4),
            "taxblAmtEcm": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ecm'), 4),
            "taxblAmtExeeg": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Exeeg'), 4),
            "taxblAmtTot": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Tot'), 4),
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
            "taxAmtA": round(self.calculate_tax_amount(self.invoice_line_ids, 'A'), 4),
            "taxAmtB": round(self.calculate_tax_amount(self.invoice_line_ids, 'B'), 4),
            "taxAmtC": round(self.calculate_tax_amount(self.invoice_line_ids, 'C'), 4),
            "taxAmtC1": round(self.calculate_tax_amount(self.invoice_line_ids, 'C1'), 4),
            "taxAmtC2": round(self.calculate_tax_amount(self.invoice_line_ids, 'C2'), 4),
            "taxAmtC3": round(self.calculate_tax_amount(self.invoice_line_ids, 'C3'), 4),
            "taxAmtD": round(self.calculate_tax_amount(self.invoice_line_ids, 'D'), 4),
            "taxAmtRvat": round(self.calculate_tax_amount(self.invoice_line_ids, 'Rvat'), 4),
            "taxAmtE": round(self.calculate_tax_amount(self.invoice_line_ids, 'E'), 4),
            "taxAmtF": round(self.calculate_tax_amount(self.invoice_line_ids, 'F'), 4),
            "taxAmtIpl1": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ipl1'), 4),
            "taxAmtIpl2": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ipl2'), 4),
            "taxAmtTl": round(self.calculate_tax_amount(self.invoice_line_ids, 'Tl'), 4),
            "taxAmtEcm": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ecm'), 4),
            "taxAmtExeeg": round(self.calculate_tax_amount(self.invoice_line_ids, 'Exeeg'), 4),
            "taxAmtTot": round(self.calculate_tax_amount(self.invoice_line_ids, 'Tot'), 4),
            "totTaxblAmt": round(totTaxblAmt, 4),
            "totTaxAmt": round(totTaxAmt, 4),
            "totAmt": round(totAmt, 4),
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
            "destnCountryCd": export_country_code,
            "dbtRsnCd": "",
            "invcAdjustReason": "",
            "itemList": item_list
        }

        return payload

    def _post_to_api(self, url, payload, success_message_prefix):
        try:
            payload_json = json.dumps(payload, indent=4)
            _logger.info(payload_json)
            # Send the POST request
            response = requests.post(url, json=payload)

            # Print and log the response status code
            print(f'API responded with status code: {response.status_code}')
            _logger.info(f'API responded with status code: {response.status_code}')

            # Raise an error for bad responses
            response.raise_for_status()  # This will raise an HTTPError if the status is 4xx or 5xx

            # Attempt to parse the JSON response
            response_data = response.json()
            print(f'API Response: {response_data}')  # Print the entire response for debugging

            result_cd = response_data.get('resultCd', 'No result code returned')
            result_msg = response_data.get('resultMsg', 'No result message returned')
            data = response_data.get('data')

            # Raise an error if the result code is not '000'
            if result_cd != '000':
                raise UserError(f"API Error - {result_msg} (Result Code: {result_cd})")

            # If result code is '000', process the data as before
            if data:
                rcpt_no = data.get('rcptNo')
                intrl_data = data.get('intrlData')
                rcpt_sign = data.get('rcptSign')
                vsdc_rcpt_pbct_date = data.get('vsdcRcptPbctDate')
                sdc_id = data.get('sdcId')
                mrc_no = data.get('mrcNo')
                qr_code_url = data.get('qrCodeUrl')

                # Log the extracted response data
                print(f'Response Data - rcpt_no: {rcpt_no}, intrl_data: {intrl_data}, rcpt_sign: {rcpt_sign}, '
                      f'vsdc_rcpt_pbct_date: {vsdc_rcpt_pbct_date}, sdc_id: {sdc_id}, mrc_no: {mrc_no}, '
                      f'qr_code_url: {qr_code_url}')

                # Update the record with response data
                if self:
                    record = self[0]
                    record.message_post(body=f"{success_message_prefix}: {result_msg}")
                    _logger.info(f'{success_message_prefix}: {result_msg}')
                    print(f'{success_message_prefix}: {result_msg}')

                    # Update the record with response data
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

        except requests.exceptions.HTTPError as http_err:
            _logger.error(f'HTTP error occurred: {str(http_err)}')
            print(f'HTTP error occurred: {str(http_err)}')
            raise UserError(f"API HTTP error occurred: {str(http_err)}")
        except requests.exceptions.ConnectionError as conn_err:
            _logger.error(f'Connection error occurred: {str(conn_err)}')
            print(f'Connection error occurred: {str(conn_err)}')
            raise UserError(f"API Connection error occurred: {str(conn_err)}")
        except requests.exceptions.Timeout as timeout_err:
            _logger.error(f'Timeout error occurred: {str(timeout_err)}')
            print(f'Timeout error occurred: {str(timeout_err)}')
            raise UserError(f"API Timeout error occurred: {str(timeout_err)}")
        except requests.exceptions.RequestException as req_err:
            _logger.error(f'API request failed: {str(req_err)}')
            print(f'API request failed: {str(req_err)}')
            raise UserError(f"API request failed: {str(req_err)}")

    def _post_to_stock_api(self, url, payload, success_message_prefix):
        _logger.info(payload)

        print('Stock Payload being sent:', json.dumps(payload, indent=4))
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
        tpin, lpo, export_country_code = self.get_sales_order_fields()
        print(f"Original Reference in debit_note_payload: {original_ref}")
        debit_move = self.env['account.move'].browse(self._context.get('active_id'))
        rcpt_no = self.get_debit_receipt_no(original_ref)
        print(f"Receipt Number: {rcpt_no}")

        local_tz = pytz.timezone("Africa/Lusaka")  # e.g., 'America/New_York'
        now = datetime.now(local_tz)
        date_prefix = now.strftime('%Y/%m/%d/%H:%M:%S')  # Formats as YYYY/mm/dd/HH:MM:SS
        sequence_number = self.env['ir.sequence'].next_by_code('account.move')  # Generates the next sequence number
        if self.name.startswith('INV/') and '/' in self.name:
            sequence_number = self.name.split('/')[-1]  # Get the last part, which is the numeric sequence
        cisInvcNo_value = f'INV/{date_prefix}/{sequence_number}'

        debit_reversal_id = self._context.get('active_id')
        debit_reversal_move = self.env['account.debit.note'].browse(debit_reversal_id)
        debit_note_reason = debit_reversal_move.reason if debit_reversal_move else "01"
        print(f'Fetched Reversal Reason: {debit_note_reason}')

        customer = self.partner_id
        custTpin = (
                tpin or  # Use tpin from the current record
                (customer.vat) or  # Use tax_id from customer
                "1000000000"  # Default fallback value
        )

        sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
        lpo = sale_order.lpo if sale_order else None
        export_country_code = sale_order.export_country_id.code if sale_order and sale_order.export_country_id else None
        exchange_rate = self.get_exchange_rate(self.currency_id, self.env.company.currency_id)
        item_list = []
        for index, line in enumerate(self.invoice_line_ids):
            tax_rate = sum(line.tax_ids.mapped('amount')) / 100
            item_price_with_tax_incl = line.price_unit * (1 + tax_rate)
            # item_sply_amount_incl = line.quantity * round(item_price_with_tax, 4)
            item_sply_amount = (line.quantity) * (line.price_unit)
            item_discount_amount = ((item_sply_amount) * (line.discount / 100))
            item_net_sply_amount = (item_sply_amount) - (round(item_discount_amount, 2))
            vat_taxbleAmt = item_net_sply_amount / (1 + tax_rate)
            vat_Amt = vat_taxbleAmt * tax_rate
            tot_Amt = item_net_sply_amount

            item_list.append({
                "itemSeq": index + 1,
                "itemCd": line.product_id.product_tmpl_id.item_Cd,
                "itemClsCd": line.product_id.product_tmpl_id.item_cls_cd,
                "itemNm": line.product_id.name,
                "bcd": line.product_id.barcode,
                "pkgUnitCd": line.product_id.product_tmpl_id.packaging_unit_cd,
                "pkg": line.quantity,
                "qtyUnitCd": line.product_id.product_tmpl_id.quantity_unit_cd,
                "qty": round(line.quantity, 4),
                "prc": round(line.price_unit, 4),
                "splyAmt": round(item_sply_amount, 4),
                "dcRt": line.discount,
                "dcAmt": round(item_discount_amount, 2),
                "isrccCd": "",
                "isrccNm": "",
                "isrcRt": 0.0,
                "isrcAmt": 0.0,
                "vatCatCd": self.get_tax_description(line.tax_ids),
                "exciseTxCatCd": None,
                "vatTaxblAmt": round(vat_taxbleAmt, 4),
                "exciseTaxblAmt": 0.0,
                "vatAmt": round(vat_Amt, 4),
                "exciseTxAmt": 0.0,
                "totAmt": round(tot_Amt, 4),
            })

        # Summary amounts
        totTaxblAmt = sum(item['vatTaxblAmt'] for item in item_list)
        totTaxAmt = sum(item['vatAmt'] for item in item_list)
        totAmt = sum(item['totAmt'] for item in item_list)
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "orgSdcId": company.org_sdc_id,
            "orgInvcNo": rcpt_no,
            "cisInvcNo": cisInvcNo_value,
            "custTpin": custTpin,
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
            "taxblAmtA": round(self.calculate_taxable_amount(self.invoice_line_ids, 'A'), 4),
            "taxblAmtB": round(self.calculate_taxable_amount(self.invoice_line_ids, 'B'), 4),
            "taxblAmtC": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C'), 4),
            "taxblAmtC1": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C1'), 4),
            "taxblAmtC2": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C2'), 4),
            "taxblAmtC3": round(self.calculate_taxable_amount(self.invoice_line_ids, 'C3'), 4),
            "taxblAmtD": round(self.calculate_taxable_amount(self.invoice_line_ids, 'D'), 4),
            "taxblAmtRvat": round(self.calculate_taxable_amount(self.invoice_line_ids, 'RVAT'), 4),
            "taxblAmtE": round(self.calculate_taxable_amount(self.invoice_line_ids, 'E'), 4),
            "taxblAmtF": round(self.calculate_taxable_amount(self.invoice_line_ids, 'F'), 4),
            "taxblAmtIpl1": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl1'), 4),
            "taxblAmtIpl2": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ipl2'), 4),
            "taxblAmtTl": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Tl'), 4),
            "taxblAmtEcm": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Ecm'), 4),
            "taxblAmtExeeg": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Exeeg'), 4),
            "taxblAmtTot": round(self.calculate_taxable_amount(self.invoice_line_ids, 'Tot'), 4),
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
            "taxAmtA": round(self.calculate_tax_amount(self.invoice_line_ids, 'A'), 4),
            "taxAmtB": round(self.calculate_tax_amount(self.invoice_line_ids, 'B'), 4),
            "taxAmtC": round(self.calculate_tax_amount(self.invoice_line_ids, 'C'), 4),
            "taxAmtC1": round(self.calculate_tax_amount(self.invoice_line_ids, 'C1'), 4),
            "taxAmtC2": round(self.calculate_tax_amount(self.invoice_line_ids, 'C2'), 4),
            "taxAmtC3": round(self.calculate_tax_amount(self.invoice_line_ids, 'C3'), 4),
            "taxAmtD": round(self.calculate_tax_amount(self.invoice_line_ids, 'D'), 4),
            "taxAmtRvat": round(self.calculate_tax_amount(self.invoice_line_ids, 'Rvat'), 4),
            "taxAmtE": round(self.calculate_tax_amount(self.invoice_line_ids, 'E'), 4),
            "taxAmtF": round(self.calculate_tax_amount(self.invoice_line_ids, 'F'), 4),
            "taxAmtIpl1": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ipl1'), 4),
            "taxAmtIpl2": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ipl2'), 4),
            "taxAmtTl": round(self.calculate_tax_amount(self.invoice_line_ids, 'Tl'), 4),
            "taxAmtEcm": round(self.calculate_tax_amount(self.invoice_line_ids, 'Ecm'), 4),
            "taxAmtExeeg": round(self.calculate_tax_amount(self.invoice_line_ids, 'Exeeg'), 4),
            "taxAmtTot": round(self.calculate_tax_amount(self.invoice_line_ids, 'Tot'), 4),
            "totTaxblAmt": round(totTaxblAmt, 4),
            "totTaxAmt": round(totTaxAmt, 4),
            "totAmt": round(totAmt, 4),
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
            "destnCountryCd": export_country_code,
            "dbtRsnCd": debit_note_reason or "02",
            "invcAdjustReason": "",
            "itemList": item_list
        }

        return payload

    @api.constrains('tpin')
    def _check_tpin(self):
        for move in self:
            if move.tpin and (not move.tpin.isdigit() or len(move.tpin) != 10):
                raise ValidationError(_('Invalid TPIN. It must consist of exactly 10 digits.'))

    @api.onchange('partner_id')
    def _change_partner_id_tpin(self):
        """ Auto-update the TPIN when a customer is selected if the partner has a tax ID """
        if self.partner_id:
            # Check if the partner has a TPIN and update it on the move
            self.tpin = self.partner_id.vat or ''


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
    journal_id = fields.Many2one('account.journal', 'Journal', required=True, default=lambda self: self._get_default_journal())
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
        journal = self.env['account.journal'].search(['|', ('type', '=', 'sale'), ('type', '=', 'purchase')], limit=1)
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
