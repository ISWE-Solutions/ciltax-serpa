from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.exceptions import ValidationError
import requests
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)

fetch_options_counter = 0
fetch_purchase_data_counter = 0
fetch_counter = 0

fetch_options_cache = None
fetch_options_last_request = None
fetch_data_cache = None


class PurchaseData(models.Model):
    _name = 'purchase.data'
    _description = 'Purchase Data'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    spplr_tpin = fields.Char(string='Supplier TPIN')
    item_nms = fields.Char(string='item name ')
    spplr_nm = fields.Char(string='Supplier Name')
    spplr_bhf_id = fields.Char(string='Supplier BHF ID')
    spplr_invc_no = fields.Integer(string='Invoice No')
    rcpt_ty_cd = fields.Char(string='Receipt Type Code')
    pmt_ty_cd = fields.Char(string='Payment Type Code')
    cfm_dt = fields.Datetime(string='Confirmation Date')
    sales_dt = fields.Date(string='Sales Date')
    stock_rls_dt = fields.Datetime(string='Stock Release Date')
    tot_item_cnt = fields.Integer(string='Total Item Count')
    tot_taxbl_amt = fields.Float(string='Total Taxable Amount')
    quantity_unit_cd = fields.Char(string="Quantity Unit Code")
    cd = fields.Char(string='Country Code')
    item_nm = fields.Char(string='Item Name')
    location_id = fields.Many2one('stock.location', string='Location', required=False)
    tot_tax_amt = fields.Float(string='Total Tax Amount')
    tot_amt = fields.Float(string='Total Amount')
    remark = fields.Text(string='Remark')
    item_list = fields.One2many('purchase.item', 'purchase_id', string='Item List')
    fetched = fields.Boolean(string="Fetched", default=False)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('partial', 'Partial'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft')

    fetch_selection = fields.Selection(
        string='Select Data to Fetch',
        selection='_get_fetch_options',
        required=False,
    )

    fetch_selection_field_2 = fields.Many2one(
        'fetched.data',  # Reference the fetched.data model
        string='Select Fetched Data',
        required=False,
        domain=[],  # Add a domain if you want to filter the available records
    )

    def action_fetch_data(self):
        self._fetch_data_from_endpoint()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Fetched Data',
            'res_model': 'fetched.data',
            'view_mode': 'tree,form',
            'target': 'current',
        }

    # def _fetch_data_from_endpoint(self):
    #     global fetch_counter, fetch_data_cache, fetch_options_last_request
    #
    #     # Unlink existing records in 'fetched.data'
    #     self.env['fetched.data'].search([]).unlink()
    #
    #     # Check if the cache is valid
    #     if fetch_data_cache is not None and fetch_options_last_request == "20240105210300":
    #         return fetch_data_cache
    #
    #     fetch_counter += 1
    #     url = "http://vsdc.iswe.co.zm/sandbox/trnsPurchase/selectTrnsPurchaseSales"
    #     headers = {'Content-Type': 'application/json'}
    #     payload = {
    #         "tpin": company.tpin,
    #         "bhfId": company.bhf_id,
    #         "lastReqDt": "20240105210300"
    #     }
    #
    #     try:
    #         response = requests.post(url, data=json.dumps(payload), headers=headers)
    #         response.raise_for_status()
    #     except requests.exceptions.RequestException as e:
    #         print('Error fetching data:', e)
    #         return None
    #
    #     try:
    #         result = response.json()
    #         print("Fetched result:", result)  # Print the fetched result for debugging
    #     except ValueError as e:
    #         print('Error parsing JSON response:', e)
    #         return None
    #
    #     if result.get('resultCd') == '000':
    #         data = result['data']
    #         print("Sale List:", data['saleList'])  # Print the sale list for debugging
    #         self._store_fetched_data(data['saleList'])
    #         return data
    #     else:
    #         print('Failed to fetch data:', result.get('resultMsg'))
    #         return None

    fetched_data_id = fields.Many2one('fetched.data', string='Fetched Data')

    def _store_fetched_data(self, sale_list):
        for sale in sale_list:
            try:
                # Parse the date formats as needed
                sales_date = datetime.strptime(sale.get('salesDt'), '%Y%m%d').date() if sale.get('salesDt') else False
                cfm_date = datetime.strptime(sale.get('cfmDt'), '%Y-%m-%d %H:%M:%S') if sale.get('cfmDt') else False
                stock_rls_date = datetime.strptime(sale.get('stockRlsDt'), '%Y-%m-%d %H:%M:%S') if sale.get(
                    'stockRlsDt') else False

                # Create or update fetched.data record
                fetched_record = self.env['fetched.data'].create({
                    'spplr_tpin': sale.get('spplrTpin'),
                    'spplr_nm': sale.get('spplrNm'),
                    'spplr_bhf_id': sale.get('spplrBhfId'),
                    'spplr_invc_no': sale.get('spplrInvcNo'),
                    'rcpt_ty_cd': sale.get('rcptTyCd'),
                    'pmt_ty_cd': sale.get('pmtTyCd'),
                    'cfm_dt': cfm_date,  # Use the parsed date
                    'sales_dt': sales_date,  # Use the parsed date
                    'stock_rls_dt': stock_rls_date,  # Use the parsed date
                    'tot_item_cnt': sale.get('totItemCnt'),
                    'tot_taxbl_amt': sale.get('totTaxblAmt'),
                    'tot_tax_amt': sale.get('totTaxAmt'),
                    'tot_amt': sale.get('totAmt'),
                    'remark': sale.get('remark'),
                })

                print("Created fetched.data record:", fetched_record.read())

                # Create or update purchase.item records
                for item in sale.get('itemList', []):
                    item_record = self.env['purchase.item'].create({
                        'purchase_fetch_id': fetched_record.id,
                        'item_seq': item.get('itemSeq'),
                        'item_cd': item.get('itemCd'),
                        'item_nm': item.get('itemNm'),
                        'qty': item.get('qty'),
                        'prc': item.get('prc'),
                        'sply_amt': item.get('splyAmt'),
                        'dc_rt': item.get('dcRt'),
                        'dc_amt': item.get('dcAmt'),
                        'vat_cat_cd': item.get('vatCatCd'),
                        'vat_taxbl_amt': item.get('vatTaxblAmt'),
                        'taxbl_amt': item.get('taxblAmt'),
                        'vat_amt': item.get('vatAmt'),
                        'tot_amt': item.get('totAmt'),
                        'qty_unit_cd': item.get('qtyUnitCd'),
                        'item_cls_cd': item.get('itemClsCd'),
                        'pkg_unit_cd': item.get('pkgUnitCd'),
                    })

                    print("Created purchase.item record:", item_record.read())

            except Exception as e:
                print("Error processing sale:", sale)
                print("Exception:", e)

    def log_endpoint_hits(self):
        print('Fetch Options Endpoint Hit Count: %d', fetch_options_counter)
        print('Fetch Purchase Data Endpoint Hit Count: %d', fetch_purchase_data_counter)

    def _fetch_data_from_endpoint(self):
        global fetch_counter, fetch_data_cache, fetch_options_last_request

        # Check if the cache is valid
        if fetch_data_cache is not None and fetch_options_last_request == "20240105210300":
            return fetch_data_cache

        fetch_counter += 1
        print('Fetch Endpoint Hit Count:', fetch_counter)

        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        url = config_settings.purchase_si_endpoint
        headers = {'Content-Type': 'application/json'}
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "lastReqDt": "20240105210300"
        }

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print('Error fetching data:', e)
            return None

        try:
            result = response.json()
        except ValueError as e:
            print('Error parsing JSON response:', e)
            return None

        if result.get('resultCd') == '000':
            fetch_data_cache = result['data']
            fetch_options_last_request = "20240105210300"
            return result['data']
        else:
            print('Failed to fetch data:', result.get('resultMsg'))
            return None

    def _get_fetch_options(self):
        global fetch_options_cache, fetch_options_last_request

        if fetch_options_cache is None or fetch_options_last_request != "20240105210300":
            data = self._fetch_data_from_endpoint()
            if data is None:
                return []

            sale_list = data.get('saleList', [])
            existing_invoices = self.search([]).mapped('spplr_invc_no')
            new_options = []
            for sale in sale_list:
                if sale['spplrInvcNo'] and sale['spplrInvcNo'] not in existing_invoices:
                    item_nm = sale['itemList'][0]['itemNm'] if sale['itemList'] else 'No Item'
                    option_label = f"{sale['spplrNm']} - {sale['spplrTpin']} - {item_nm}"
                    new_options.append((str(sale['spplrInvcNo']), option_label))
            fetch_options_cache = new_options
            fetch_options_last_request = "20240105210300"

        return fetch_options_cache

    # def fetch_purchase_data(self, *args, **kwargs):
    #     _logger.info(f"Fetching data for purchase record with ID: {self.id}")
    #     _logger.info(f"Selected Fetched Data ID: {self.fetch_selection_field_2.id}")
    #
    #     if len(self) > 1:
    #         raise ValueError("This operation can only be performed on one record at a time.")
    #
    #     if not self.fetch_selection_field_2:
    #         _logger.warning("No data selected to fetch.")
    #         return {
    #             'type': 'ir.actions.client',
    #             'tag': 'display_notification',
    #             'params': {
    #                 'title': 'Error',
    #                 'message': 'Please select data to fetch.',
    #                 'type': 'danger',
    #             }
    #         }
    #
    #     fetched_data = self.fetch_selection_field_2
    #
    #     # Log the entire fetched_data structure
    #     _logger.info(f"Fetched Data: {fetched_data.read()}")
    #
    #     # Concatenate the item names
    #     item_names = ', '.join([item.item_nm for item in fetched_data.item_list])
    #
    #     purchase_data_vals = {
    #         'spplr_nm': fetched_data.spplr_nm,
    #         'spplr_tpin': fetched_data.spplr_tpin,
    #         'spplr_invc_no': fetched_data.spplr_invc_no,
    #         'tot_amt': fetched_data.tot_amt,
    #         'spplr_bhf_id': fetched_data.spplr_bhf_id,
    #         'rcpt_ty_cd': fetched_data.rcpt_ty_cd,
    #         'pmt_ty_cd': fetched_data.pmt_ty_cd,
    #         'tot_tax_amt': fetched_data.tot_tax_amt,
    #         'remark': fetched_data.remark,
    #         'cfm_dt': fetched_data.cfm_dt,
    #         'sales_dt': fetched_data.sales_dt,
    #         'stock_rls_dt': fetched_data.stock_rls_dt,
    #         'item_nm': item_names,  # Store concatenated item names
    #     }
    #
    #     purchase_data_record = self.env['purchase.data'].create(purchase_data_vals)
    #     _logger.info(f"Created Purchase Data ID: {purchase_data_record.id}")
    #
    #     for item in fetched_data.item_list:
    #         self.env['purchase.item'].create({
    #             'purchase_id': purchase_data_record.id,
    #             'purchase_fetch_id': fetched_data.id,
    #             'item_seq': item.item_seq,
    #             'item_cd': item.item_cd,
    #             'item_nm': item.item_nm,
    #             'qty': item.qty,
    #             'fetched': item.qty,
    #             'prc': item.prc,
    #             'sply_amt': item.sply_amt,
    #             'dc_rt': item.dc_rt,
    #             'dc_amt': item.dc_amt,
    #             'vat_taxbl_amt': item.vat_taxbl_amt,
    #             'taxbl_amt': item.taxbl_amt,
    #             'vat_amt': item.vat_amt,
    #             'tot_amt': item.tot_amt,
    #             'vat_cat_cd': item.vat_cat_cd,
    #             'qty_unit_cd': item.qty_unit_cd,
    #             'item_cls_cd': item.item_cls_cd,
    #             'pkg_unit_cd': item.pkg_unit_cd,
    #         })
    #
    #     _logger.info(f"Purchase items created for purchase data ID: {purchase_data_record.id}")
    #
    #     return {
    #         'type': 'ir.actions.act_window',
    #         'res_model': 'purchase.data',
    #         'view_mode': 'tree,form',
    #         'target': 'current',
    #         'context': {'search_default_filter': True},
    #     }

    def fetch_purchase_data(self):
        selected_option = self.fetch_selection
        if not selected_option:
            raise UserError(_('Please select an option to fetch data.'))

        data = self._fetch_data_from_endpoint()
        if data is None:
            raise UserError(_('Failed to fetch data from the endpoint.'))

        selected_invoice_number = int(selected_option)
        for sale in data['saleList']:
            if sale['spplrInvcNo'] == selected_invoice_number:
                self.spplr_tpin = sale['spplrTpin']
                self.spplr_nm = sale['spplrNm']
                self.spplr_bhf_id = sale['spplrBhfId']
                self.spplr_invc_no = sale['spplrInvcNo']
                self.rcpt_ty_cd = sale['rcptTyCd']
                self.pmt_ty_cd = sale['pmtTyCd']
                self.item_nm = sale['itemList'][0]['itemNm']

                def parse_date(date_str):
                    if not date_str:
                        return None
                    for fmt in ('%Y%m%d%H%M%S', '%Y-%m-%d %H:%M:%S', '%Y%m%d'):
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            pass
                    raise ValueError(f"Date format for {date_str} is not supported")

                self.cfm_dt = parse_date(sale['cfmDt']) if sale.get('cfmDt') else None
                self.sales_dt = parse_date(sale['salesDt']).date() if sale.get('salesDt') else None
                self.stock_rls_dt = parse_date(sale['stockRlsDt']) if sale.get('stockRlsDt') else None

                self.tot_item_cnt = sale['totItemCnt']
                self.tot_taxbl_amt = sale['totTaxblAmt']
                self.tot_tax_amt = sale['totTaxAmt']
                self.tot_amt = sale['totAmt']
                self.remark = sale.get('remark', '')

                items = [(0, 0, {
                    'item_seq': item['itemSeq'],
                    'item_cd': item['itemCd'],
                    'item_nm': item['itemNm'],
                    'qty': item['qty'],
                    'fetched': item['qty'],
                    'prc': item['prc'],
                    'vat_cat_cd': item['vatCatCd'],
                    'tot_amt': item['totAmt'],
                    'qty_unit_cd': item['qtyUnitCd'],
                    'item_cls_cd': item['itemClsCd'],
                    'pkg_unit_cd': item['pkgUnitCd'],
                }) for item in sale['itemList']]
                self.item_list = items
                self.fetched = True
                break
        else:
            raise UserError(_('Selected invoice not found in the fetched data.'))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Purchase Data',
            'view_mode': 'tree,form',
            'res_model': 'purchase.data',
            'views': [
                (self.env.ref('zra_smart_invoice.view_purchase_data_tree').id, 'tree'),
                (self.env.ref('zra_smart_invoice.view_purchase_data_form').id, 'form')
            ],
            'target': 'current',
        }

    # To log the count whenever needed, you can add a separate method
    def print_endpoint_hits(self):
        print('Fetch Options Endpoint Hit Count:', fetch_options_counter)
        print('Fetch Purchase Data Endpoint Hit Count:', fetch_purchase_data_counter)

    def get_product_quantities(self):
        product_quantities = {}
        for item in self.item_list:
            product_template = self.env['product.template'].search(
                [('item_Cd', '=', item.item_cd), ('name', '=', item.item_nm)], limit=1)
            if product_template:
                product = self.env['product.product'].search([('product_tmpl_id', '=', product_template.id)], limit=1)
                if product:
                    stock_quant = self.env['stock.quant'].search(
                        [('product_id', '=', product.id), ('location_id', '=', self.location_id.id)], limit=1)
                    quantity = stock_quant.quantity if stock_quant else 0
                    product_quantities[(item.item_cd, item.item_nm)] = quantity
                    print(f"Product Name: {item.item_nm}, Item Code: {item.item_cd}, Quantity: {quantity}")
                else:
                    product_quantities[(item.item_cd, item.item_nm)] = 0
                    print(f"Product Name: {item.item_nm}, Item Code: {item.item_cd}, Quantity: 0")
            else:
                product_quantities[(item.item_cd, item.item_nm)] = 0
                print(f"Product Name: {item.item_nm}, Item Code: {item.item_cd}, Quantity: 0")

        return product_quantities

    def fetch_existing_quantities(self):
        product_quantities = {}
        for item in self.item_list:
            product_template = self.env['product.template'].search(
                [('name', '=', item.item_nm)], limit=1)
            if product_template:
                product = self.env['product.product'].search([('product_tmpl_id', '=', product_template.id)], limit=1)
                if product:
                    stock_quant = self.env['stock.quant'].search(
                        [('product_id', '=', product.id),
                         ('location_id', '=', self.env.ref('stock.stock_location_stock').id)], limit=1)
                    quantity = stock_quant.quantity if stock_quant else 0
                    product_quantities[item.item_nm] = quantity
                    print(f"Product Name: {item.item_nm}, Quantity: {quantity}")
                else:
                    product_quantities[item.item_nm] = 0
                    print(f"Product Name: {item.item_nm}, Quantity: 0")
            else:
                product_quantities[item.item_nm] = 0
                print(f"Product Name: {item.item_nm}, Quantity: 0")

        return product_quantities

    def get_total_quantities(self):
        product_quantities = {}
        for item in self.item_list:
            product_template = self.env['product.template'].search(
                [('item_Cd', '=', item.item_cd), ('name', '=', item.item_nm)], limit=1)
            if product_template:
                product = self.env['product.product'].search([('product_tmpl_id', '=', product_template.id)], limit=1)
                if product:
                    stock_quant = self.env['stock.quant'].search(
                        [('product_id', '=', product.id), ('location_id', '=', self.location_id.id)], limit=1)
                    quantity = stock_quant.quantity if stock_quant else 0
                    product_quantities[(item.item_cd, item.item_nm)] = quantity + item.qty
                    print(
                        f"Product Name: {item.item_nm}, Item Code: {item.item_cd}, Quantity: {quantity}, Total: {quantity + item.qty}")
                else:
                    product_quantities[(item.item_cd, item.item_nm)] = item.qty
                    print(f"Product Name: {item.item_nm}, Item Code: {item.item_cd}, Quantity: 0, Total: {item.qty}")
            else:
                product_quantities[(item.item_cd, item.item_nm)] = item.qty
                print(f"Product Name: {item.item_nm}, Item Code: {item.item_cd}, Quantity: 0, Total: {item.qty}")

        return product_quantities

    def refresh_list(self):

        global fetch_options_cache, fetch_options_last_request

        fetch_options_cache = None
        fetch_options_last_request = None
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def confirm_invoice(self):

        global fetch_options_cache, fetch_options_last_request

        fetch_options_cache = None
        fetch_options_last_request = None
        self.ensure_one()

        if not self.item_list:
            raise UserError(_('No items to confirm.'))

        all_confirmed = True
        all_rejected = True
        io_confirmed_items = []
        io_rejected_items = []
        confirmed_items = []
        rejected_items = []
        confirmed_stock_items = []
        rejected_stock_items = []
        confirmed_io_items = []
        rejected_io_items = []

        product_quantities = self.fetch_existing_quantities()

        for item in self.item_list:
            confirmed_qty = item.qty
            fetched_qty = item.fetched
            rejected_qty = fetched_qty - confirmed_qty

            # Get the existing quantity using both item_cd and name
            existing_qty = product_quantities.get(item.item_nm, 0)

            # Calculate the total quantity
            total_qty = existing_qty + confirmed_qty

            print(
                f"Fetched: {fetched_qty}, Confirmed: {confirmed_qty}, Rejected: {rejected_qty}, Existing: {existing_qty}, Total: {total_qty}")

            if confirmed_qty == 0:
                rejected_items.append(item)
                io_rejected_items.append(item)
            else:
                confirmed_items.append(item)
                io_confirmed_items.append(item)
                confirmed_stock_items.append({
                    "itemCd": item.item_cd,
                    "rsdQty": total_qty
                })

                confirmed_io_items.append({
                    "itemSeq": item.item_seq,
                    "itemCd": item.item_cd,
                    "itemClsCd": item.item_cls_cd,
                    "itemNm": item.item_nm,
                    "bcd": item.bcd,
                    "pkgUnitCd": item.pkg_unit_cd if item.pkg_unit_cd else 'NT',
                    "pkg": item.pkg,
                    "qtyUnitCd": item.qty_unit_cd if item.qty_unit_cd else 'U',
                    "qty": confirmed_qty or item.qty,
                    "itemExprDt": item.item_expr_dt if item.item_expr_dt else None,
                    "prc": item.prc,
                    "splyAmt": item.sply_amt,
                    "totDcAmt": item.tot_dc_amt,
                    "taxblAmt": item.taxbl_amt if item.taxbl_amt else 0,
                    "vatCatCd": item.vat_cat_cd if item.vat_cat_cd else 'A',
                    "iplCatCd": item.ipl_cat_cd if item.ipl_cat_cd else 'IPL1',
                    "tlCatCd": item.tl_cat_cd if item.tl_cat_cd else 'TL',
                    "exciseTxCatCd": item.excise_tx_cat_cd if item.excise_tx_cat_cd else 'EXEEG',
                    "vatAmt": item.vat_amt,
                    "iplAmt": item.ipl_amt,
                    "tlAmt": item.tl_amt,
                    "exciseTxAmt": item.excise_tx_amt,
                    "taxAmt": item.tax_amt if item.tax_amt else 16,
                    "totAmt": item.tot_amt
                })

                all_rejected = False

            if rejected_qty > 0:
                rejected_items.append(item)
                io_rejected_items.append(item)
                rejected_stock_items.append({
                    "itemCd": item.item_cd,
                    "rsdQty": rejected_qty
                })

                rejected_io_items.append({
                    "itemSeq": item.item_seq,
                    "itemCd": item.item_cd,
                    "itemClsCd": item.item_cls_cd,
                    "itemNm": item.item_nm,
                    "bcd": item.bcd,
                    "pkgUnitCd": item.pkg_unit_cd if item.pkg_unit_cd else 'NT',
                    "pkg": item.pkg,
                    "qtyUnitCd": item.qty_unit_cd if item.qty_unit_cd else 'U',
                    "qty": rejected_qty or item.qty,
                    "itemExprDt": item.item_expr_dt if item.item_expr_dt else None,
                    "prc": item.prc,
                    "splyAmt": item.sply_amt,
                    "totDcAmt": item.tot_dc_amt,
                    "taxblAmt": item.taxbl_amt if item.taxbl_amt else 0,
                    "vatCatCd": item.vat_cat_cd if item.vat_cat_cd else 'A',
                    "iplCatCd": item.ipl_cat_cd if item.ipl_cat_cd else 'IPL1',
                    "tlCatCd": item.tl_cat_cd if item.tl_cat_cd else 'TL',
                    "exciseTxCatCd": item.excise_tx_cat_cd if item.excise_tx_cat_cd else 'EXEEG',
                    "vatAmt": item.vat_amt,
                    "iplAmt": item.ipl_amt,
                    "tlAmt": item.tl_amt,
                    "exciseTxAmt": item.excise_tx_amt,
                    "taxAmt": item.tax_amt if item.tax_amt else 16,
                    "totAmt": item.tot_amt
                })

                all_confirmed = False

        if all_confirmed:
            print('All items are confirmed.')
            self._save_purchase()
            self._save_item_full_confirmed()
            self._save_stock_master_full_confirmed()
            self.status = 'confirmed'
        elif all_rejected:
            print('All items are rejected.')
            self._reject_purchase()
            self.status = 'rejected'
        else:
            print('Partial confirmation.')
            self._save_purchase()

            # print("Saving confirmed items with stock master payload:")
            self._save_item(confirmed_io_items)

            # print("Saving confirmed items with stock master payload:")
            self._save_stock_master(confirmed_stock_items)

            self._reject_purchase()

            # print("Saving rejected items with stock master payload:")
            # self._save_item(rejected_io_items)

            # print("Saving rejected items with stock master payload:")
            # self._save_stock_master(rejected_stock_items)

            self.status = 'partial'

        self.create_or_update_products()

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'purchase.data',
            'res_id': self.id,
            'target': 'current',
            'flags': {'form_view_initial_mode': 'edit'},
            'context': self.env.context,
        }

    def create_or_update_products(self):
        product_template_model = self.env['product.template']
        product_product_model = self.env['product.product']
        stock_quant_model = self.env['stock.quant']
        stock_location = self.env.ref('stock.stock_location_stock')

        for item in self.item_list:
            product_name = item.item_nm

            if not product_name:
                continue

            # Check if product template exists, or create a new one
            existing_template = product_template_model.search([('name', '=', product_name)], limit=1)
            template_values = {
                'name': item.item_nm,
                'type': 'product',
                'list_price': item.prc,
                'quantity_unit_cd': item.qty_unit_cd,
                'item_cls_cd': item.item_cls_cd,
                'packaging_unit_cd': item.pkg_unit_cd,
                'item_Cd': item.item_cd,
                'cd': 'ZM',
                'use_yn': 'Y',
            }

            if existing_template:
                # Update existing product template
                # print(f'Updating existing product template {existing_template.name} with values: {template_values}')
                existing_template.write(template_values)
            else:
                # Create new product template
                # print(f'Creating new product template with values: {template_values}')
                existing_template = product_template_model.create(template_values)

            # Ensure the product variant exists
            product_variant = product_product_model.search([('product_tmpl_id', '=', existing_template.id)], limit=1)
            if not product_variant:
                product_variant = product_product_model.create({'product_tmpl_id': existing_template.id})

            # Update or create stock quant
            stock_quant = stock_quant_model.search([
                ('product_id', '=', product_variant.id),
                ('location_id', '=', stock_location.id)
            ], limit=1)

            if stock_quant:
                new_quantity = stock_quant.quantity + item.qty
                stock_quant.write({'quantity': new_quantity})
                # print(f'Updated stock quant for {product_variant.name}, new quantity: {new_quantity}')
            else:
                stock_quant_model.create({
                    'product_id': product_variant.id,
                    'location_id': stock_location.id,
                    'quantity': item.qty,
                })
                # print(f'Created new stock quant for {product_variant.name} with quantity: {item.qty}')

        # Optionally, commit the transaction if necessary
        self.env.cr.commit()

    def reject_purchase(self):
        self._reject_purchase()
        # self.status = 'rejected'
        _logger.info('Invoice confirmed for supplier invoice no: %s', self.spplr_invc_no)

    def _reject_purchase(self, item=None):
        company = self.env.company
        if not self.item_list:
            raise UserError(_('No items to confirm.'))

        confirmed_qty = sum(item.qty for item in self.item_list)
        fetched_qty = sum(item.fetched for item in self.item_list)
        rejected_qty = fetched_qty - confirmed_qty

        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        url = config_settings.purchase_endpoint
        headers = {'Content-Type': 'application/json'}
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "invcNo": self.spplr_invc_no,
            "orgInvcNo": 0,
            "spplrTpin": self.spplr_tpin,
            "spplrBhfId": self.spplr_bhf_id,
            "spplrNm": self.spplr_nm,
            "spplrInvcNo": self.spplr_invc_no,
            "regTyCd": 'A',
            "pchsTyCd": "N",
            "rcptTyCd": "R",
            "pmtTyCd": self.pmt_ty_cd,
            "pchsSttsCd": "02",
            "cfmDt": self.cfm_dt.strftime('%Y%m%d%H%M%S'),
            "pchsDt": self.cfm_dt.strftime('%Y%m%d'),
            "wrhsDt": "",
            "cnclReqDt": "",
            "cnclDt": "",
            "rfdDt": "",
            "totItemCnt": self.tot_item_cnt,
            "totTaxblAmt": self.tot_taxbl_amt,
            "totTaxAmt": self.tot_tax_amt,
            "totAmt": self.tot_amt,
            "remark": self.remark or "",
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "itemList": [{
                "itemSeq": item.item_seq,
                "itemCd": item.item_cd,
                "itemClsCd": item.item_cls_cd if item.item_cls_cd else 5059690800,
                "spplrItemClsCd": item.spplr_item_cls_cd if item.spplr_item_cls_cd else None,
                "spplrItemCd": item.spplr_item_cd if item.spplr_item_cd else None,
                "spplrItemNm": item.spplr_item_nm if item.spplr_item_nm else None,
                "pkgUnitCd": item.pkg_unit_cd if item.pkg_unit_cd else 'NT',
                "itemNm": item.spplr_item_nm if item.spplr_item_nm else self.spplr_nm,
                "bcd": "",
                "pkg": item.pkg,
                "qtyUnitCd": item.qty_unit_cd if item.qty_unit_cd else 'U',
                "qty": item.qty,
                "prc": item.prc,
                "splyAmt": item.sply_amt,
                "dcRt": item.dc_rt,
                "dcAmt": item.dc_amt,
                "vatCatCd": item.vat_cat_cd if item.ipl_cat_cd else 'A',
                "iplCatCd": item.ipl_cat_cd if item.ipl_cat_cd else None,
                "tlCatCd": item.tl_cat_cd if item.tl_cat_cd else None,
                "exciseTxCatCd": item.excise_tx_cat_cd if item.excise_tx_cat_cd else None,
                "taxAmt": item.tax_amt,
                "taxblAmt": 0,
                "totAmt": item.tot_amt,
                "itemExprDt": item.item_expr_dt if item.item_expr_dt else None
            } for item in self.item_list]
        }

        # print('Payload being sent:', json.dumps(payload, indent=4))

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            print('Purchase Rejected successfully:', response.json())
        except requests.exceptions.RequestException as e:
            _logger.error('Error saving purchase: %s', e)
            if e.response:
                _logger.error('Response content: %s', e.response.content.decode())
            raise UserError(_('Error Check Network/internet Connectivity.'))

    def _save_purchase(self):
        if not self.item_list:
            raise UserError(_('No items to confirm.'))

        confirmed_qty = sum(item.qty for item in self.item_list)
        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        url = config_settings.purchase_endpoint
        headers = {'Content-Type': 'application/json'}
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "invcNo": self.spplr_invc_no,
            "orgInvcNo": 0,
            "spplrTpin": self.spplr_tpin,
            "spplrBhfId": self.spplr_bhf_id,
            "spplrNm": self.spplr_nm,
            "spplrInvcNo": self.spplr_invc_no,
            "regTyCd": 'A',
            "pchsTyCd": "N",
            "rcptTyCd": "P",
            "pmtTyCd": self.pmt_ty_cd,
            "pchsSttsCd": "02",
            "cfmDt": self.cfm_dt.strftime('%Y%m%d%H%M%S'),
            "pchsDt": self.cfm_dt.strftime('%Y%m%d'),
            "wrhsDt": "",
            "cnclReqDt": "",
            "cnclDt": "",
            "rfdDt": "",
            "totItemCnt": self.tot_item_cnt,
            "totTaxblAmt": self.tot_taxbl_amt,
            "totTaxAmt": self.tot_tax_amt,
            "totAmt": self.tot_amt,
            "remark": self.remark or "",
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "itemList": [{
                "itemSeq": item.item_seq,
                "itemCd": item.item_cd,
                "itemClsCd": item.item_cls_cd if item.item_cls_cd else 5059690800,
                "spplrItemClsCd": item.spplr_item_cls_cd if item.spplr_item_cls_cd else None,
                "spplrItemCd": item.spplr_item_cd if item.spplr_item_cd else None,
                "spplrItemNm": item.spplr_item_nm if item.spplr_item_nm else None,
                "pkgUnitCd": item.pkg_unit_cd if item.pkg_unit_cd else 'NT',
                "itemNm": item.spplr_item_nm if item.spplr_item_nm else self.spplr_nm,
                "bcd": "",
                "pkg": item.pkg,
                "qtyUnitCd": item.qty_unit_cd if item.qty_unit_cd else 'U',
                "qty": item.qty,
                "prc": item.prc,
                "splyAmt": item.sply_amt,
                "dcRt": item.dc_rt,
                "dcAmt": item.dc_amt,
                "vatCatCd": item.vat_cat_cd if item.ipl_cat_cd else 'A',
                "iplCatCd": item.ipl_cat_cd if item.ipl_cat_cd else None,
                "tlCatCd": item.tl_cat_cd if item.tl_cat_cd else None,
                "exciseTxCatCd": item.excise_tx_cat_cd if item.excise_tx_cat_cd else None,
                "taxAmt": item.tax_amt,
                "taxblAmt": 0,
                "totAmt": item.tot_amt,
                "itemExprDt": item.item_expr_dt if item.item_expr_dt else None
            } for item in self.item_list]
        }

        # print('Payload being sent:', json.dumps(payload, indent=4))

        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            print('Purchase saved successfully:', response.json())
        except requests.exceptions.RequestException as e:
            _logger.error('Error saving purchase: %s', e)
            if e.response:
                _logger.error('Response content: %s', e.response.content.decode())
            raise UserError(_('Error Check Network/internet Connectivity.'))

    def _save_item(self, stock_items):
        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        url = config_settings.stock_io_endpoint
        headers = {'Content-Type': 'application/json'}
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": None,
            "custNm": None,
            "custBhfId": self.spplr_bhf_id,
            "sarTyCd": "02",
            "ocrnDt": self.sales_dt.strftime('%Y%m%d'),
            "totItemCnt": len(self.item_list),
            "totTaxblAmt": self.tot_taxbl_amt,
            "totTaxAmt": self.tot_tax_amt,
            "totAmt": self.tot_amt,
            "remark": self.remark or "",
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "itemList": stock_items
        }
        print('Payload being sent:', json.dumps(payload, indent=4))
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            print('Stock items saved successfully:', response.json())
        except requests.exceptions.RequestException as e:
            print('Stock items failed:', response.json())
            _logger.error('Error saving stock items: %s', e)
            raise UserError(_('Failed to save stock items.'))

    def _save_stock_master(self, stock_items):
        company = self.env.company
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "stockItemList": stock_items
        }
        print("Stock master Payload being sent:", json.dumps(payload, indent=4))
        print(payload)

        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        try:
            response = requests.post(config_settings.stock_master_endpoint, data=json.dumps(payload),
                                     headers={'Content-Type': 'application/json'})
            response.raise_for_status()
            print('Stock master saved successfully:', response.json())
        except requests.exceptions.RequestException as e:
            _logger.error('Error saving stock master: %s', e)
            raise UserError(_('Failed to save stock master data.'))

    def _save_item_full_confirmed(self):
        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        url = config_settings.stock_io_endpoint
        headers = {'Content-Type': 'application/json'}
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": None,
            "custNm": None,
            "custBhfId": self.spplr_bhf_id,
            "sarTyCd": "02",
            "ocrnDt": self.sales_dt.strftime('%Y%m%d'),
            "totItemCnt": len(self.item_list),
            "totTaxblAmt": self.tot_taxbl_amt,
            "totTaxAmt": self.tot_tax_amt,
            "totAmt": self.tot_amt,
            "remark": self.remark or "",
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "itemList": [{
                "itemSeq": item.item_seq,
                "itemCd": item.item_cd,
                "itemClsCd": item.item_cls_cd if item.item_cls_cd else 5059690800,
                "itemNm": item.item_nm,
                "bcd": item.bcd,
                "pkgUnitCd": item.pkg_unit_cd if item.pkg_unit_cd else 'NT',
                "pkg": item.pkg,
                "qtyUnitCd": item.qty_unit_cd if item.qty_unit_cd else 'U',
                "qty": item.qty,
                "itemExprDt": item.item_expr_dt if item.item_expr_dt else None,
                "prc": item.prc,
                "splyAmt": item.sply_amt,
                "totDcAmt": item.tot_dc_amt,
                "taxblAmt": item.taxbl_amt if item.taxbl_amt else 0,
                "vatCatCd": item.vat_cat_cd if item.vat_cat_cd else 'A',
                "iplCatCd": item.ipl_cat_cd if item.ipl_cat_cd else 'IPL1',
                "tlCatCd": item.tl_cat_cd if item.tl_cat_cd else 'TL',
                "exciseTxCatCd": item.excise_tx_cat_cd if item.excise_tx_cat_cd else 'EXEEG',
                "vatAmt": item.vat_amt,
                "iplAmt": item.ipl_amt,
                "tlAmt": item.tl_amt,
                "exciseTxAmt": item.excise_tx_amt,
                "taxAmt": item.tax_amt if item.tax_amt else 16,
                "totAmt": item.tot_amt
            } for item in self.item_list]
        }
        # print('Payload being sent:', json.dumps(payload, indent=4))
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            print('Stock items saved successfully:', response.json())
        except requests.exceptions.RequestException as e:
            print('Stock items failed:', response.json())
            _logger.error('Error saving stock items: %s', e)
            raise UserError(_('Failed to save stock items.'))

    def _save_stock_master_full_confirmed(self):
        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        url = config_settings.stock_master_endpoint
        headers = {'Content-Type': 'application/json'}

        total_quantities = self.get_total_quantities()
        product_quantities = self.fetch_existing_quantities()

        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "stockItemList": []
        }

        for item in self.item_list:
            confirmed_qty = item.qty
            existing_qty = product_quantities.get(item.item_nm, 0)

            # Search for product template based on item name
            product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
            if product_template:
                item_cd = product_template.item_Cd
            else:
                item_cd = False

            total_qty = existing_qty + confirmed_qty
            print('existing', existing_qty)
            print('confirmed', confirmed_qty)

            payload["stockItemList"].append({
                "itemCd": item.item_cd or item_cd,
                "rsdQty": total_qty
            })

        print('Stock master Payload being sent:', json.dumps(payload, indent=4))
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers)
            response.raise_for_status()
            print('Stock master saved successfully:', response.json())
        except requests.exceptions.RequestException as e:
            _logger.error('Error saving stock master: %s', e)
            raise UserError(_('Failed to save stock master data.'))


class PurchaseItem(models.Model):
    _name = 'purchase.item'
    _description = 'Purchase Item'

    purchase_id = fields.Many2one('purchase.data', string='Purchase')
    # purchase_fetch_id = fields.Many2one('fetched.data', string='Fetched Data', required=True, ondelete='cascade')
    item_seq = fields.Integer(string='Item Sequence')
    item_cd = fields.Char(string='Item Code')
    item_nm = fields.Char(string='Item Name')
    qty = fields.Float(string='Accepted Quantity')
    fetched = fields.Integer(string='Received Quantity')
    prc = fields.Float(string='Price')
    dc_rt = fields.Float(string='Discount Rate')
    dc_amt = fields.Float(string='Discount Amount')
    vat_cat_cd = fields.Char(string='VAT Category Code')
    vat_taxbl_amt = fields.Float(string='VAT Taxable Amount')
    tot_amt = fields.Float(string='Total Amount')
    item_cls_cd = fields.Char(string='Item Class Code')
    spplr_item_cls_cd = fields.Char(string='Supplier Item Class Code')
    spplr_item_cd = fields.Char(string='Supplier Item Code')
    spplr_item_nm = fields.Char(string='Supplier Item Name')
    pkg_unit_cd = fields.Char(string='Package Unit Code')
    cd = fields.Char(string='Country Code')
    pkg = fields.Float(string='Package')
    qty_unit_cd = fields.Char(string='Quantity Unit Code')
    item_expr_dt = fields.Date(string='Item Expiry Date')
    sply_amt = fields.Float(string='Supply Amount')
    tot_dc_amt = fields.Float(string='Total Discount Amount')
    vat_amt = fields.Float(string='VAT Amount')
    ipl_cat_cd = fields.Char(string='IPL Category Code')
    tl_cat_cd = fields.Char(string='TL Category Code')
    excise_tx_cat_cd = fields.Char(string='Excise Tax Category Code')
    ipl_amt = fields.Float(string='IPL Amount')
    tl_amt = fields.Float(string='TL Amount')
    excise_tx_amt = fields.Float(string='Excise Tax Amount')
    tax_amt = fields.Float(string='Tax Amount')
    bcd = fields.Char(string='bcd')
    taxbl_amt = fields.Char(string='taxbl_amt')
    item_nms = fields.Char(string='item name ')
    _item_cd_options_array = []

    def values(self, *args, **kwargs):
        item_name = self.item_nm
        print(item_name)
        products = self.env['product.template'].search([('name', '=', item_name)])
        item_cd_options = [(product.item_Cd, product.item_Cd) for product in products.filtered(lambda p: p.item_Cd)]
        # Store the options in the class-level array
        type(self)._item_cd_options_array = item_cd_options
        print(item_cd_options)

        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @classmethod
    def _get_item_cd_options(cls):
        # Return the class-level array
        return cls._item_cd_options_array

    @api.constrains('qty')
    def _check_qty(self):
        for record in self:
            if record.qty < 0:
                raise ValidationError("Accepted Quantity cannot be less than 0.")
            if record.qty > record.fetched:
                raise ValidationError("Accepted Quantity cannot be greater than Received Quantity.")

    def generate_item_code(self):
        sequence = self.env['item.code.sequence'].search([], limit=1)
        if not sequence:
            sequence = self.env['item.code.sequence'].create({})
        next_number = sequence.next_number
        sequence.next_number += 1
        next_number_str = str(next_number).zfill(7)
        item_code = f"{self.item_nm[:2]}{self.pkg_unit_cd[:2]}{self.qty_unit_cd[:2]}{next_number_str}"
        # Ensure the item code is added to selection options
        products = self.env['product.template'].search([('name', '=', self.item_nm)])
        if item_code not in [product.item_Cd for product in products]:
            self.env['product.template'].create({
                'name': self.item_nm,
                'item_Cd': item_code,
            })
        # Add the generated item code to the selection options array
        type(self)._item_cd_options_array.append((item_code, item_code))
        self.item_cd = item_code
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

#
# class FetchedData(models.Model):
#     _name = 'fetched.data'
#     _description = 'Fetched Data'
#
#     spplr_tpin = fields.Char(string='Supplier TPIN')
#     spplr_nm = fields.Char(string='Supplier Name')
#     spplr_bhf_id = fields.Char(string='Supplier BHF ID')
#     spplr_invc_no = fields.Integer(string='Invoice No')
#     rcpt_ty_cd = fields.Char(string='Receipt Type Code')
#     pmt_ty_cd = fields.Char(string='Payment Type Code')
#     cfm_dt = fields.Datetime(string='Confirmation Date')
#     sales_dt = fields.Date(string='Sales Date')
#     stock_rls_dt = fields.Datetime(string='Stock Release Date')
#     tot_item_cnt = fields.Integer(string='Total Item Count')
#     tot_taxbl_amt = fields.Float(string='Total Taxable Amount')
#     tot_tax_amt = fields.Float(string='Total Tax Amount')
#     tot_amt = fields.Float(string='Total Amount')
#     remark = fields.Text(string='Remark')
#     _rec_name = 'display_name'
#     purchase_id = fields.Many2one('purchase.data', string='Purchase', ondelete='cascade')
#
#     def unlink(self):
#         purchase_items = self.env['purchase.item'].search([('purchase_fetch_id', 'in', self.ids)])
#         if purchase_items:
#             purchase_items.unlink()  # Delete related purchase items
#         return super(FetchedData, self).unlink()
#
#     display_name = fields.Char(
#         string='Display Name',
#         compute='_compute_display_name',
#         store=True
#     )
#
#     @api.depends('spplr_nm', 'spplr_tpin', 'spplr_invc_no')
#     def _compute_display_name(self):
#         for record in self:
#             name = f"{record.spplr_nm or ''} - {record.spplr_tpin or ''} - Invoice: {record.spplr_invc_no or ''}"
#             record.display_name = name
#
#     item_list = fields.One2many('purchase.item', 'purchase_fetch_id', string='Item List')
#
#
# class FetchedDataItem(models.Model):
#     _name = 'fetched.data.item'
#     _description = 'Fetched Data Items'
#
#     item_cd = fields.Char('Item Code')
#     item_nm = fields.Char('Item Name')
#     quantity = fields.Float('Quantity')
#     price = fields.Float('Price')
#     total_amount = fields.Float('Total Amount')
#     fetched_data_id = fields.Many2one('fetched.data', string='Fetched Data Reference')


class ProductProduct(models.Model):
    _inherit = 'product.product'

    quantity_unit_cd = fields.Char(string="Quantity Unit Code")
    item_cls_cd = fields.Char(string="Item Classification Code")
    packaging_unit_cd = fields.Char(string="Packaging Unit Code")
    item_Cd = fields.Char(string="Item Code")
    use_yn = fields.Char(string="Use")
