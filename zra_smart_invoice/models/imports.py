from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import requests
import json
import logging
from datetime import datetime

_logger = logging.getLogger(__name__)


compute_fetch_selection_counter = 0
fetch_import_data_counter = 0

# Initialize cache
compute_fetch_selection_cache = None
compute_fetch_selection_last_request = None


class ImportData(models.Model):
    _name = 'import.data'
    _description = 'Import Data'
    location_id = fields.Many2one('stock.location', string='Location', required=False)
    task_cd = fields.Char(string='Task Code')
    dcl_de = fields.Date(string='Declaration Date')
    dcl_no = fields.Char(string='Declaration Number')
    tot_wt = fields.Float(string='Total Weight')
    net_wt = fields.Float(string='Net Weight')
    agnt_nm = fields.Char(string='Agent Name')
    item_nm = fields.Char(string='Item Name')
    invc_fcur_amt = fields.Float(string='Invoice Foreign Currency Amount')
    invc_fcur_cd = fields.Char(string='Invoice Foreign Currency Code')
    invc_fcur_excrt = fields.Float(string='Invoice Foreign Currency Exchange Rate')
    pkg_unit_cd = fields.Char(string='Package Unit Code')
    cd = fields.Char(string='Package Unit Code')
    orgn_nat_cd = fields.Char(string='original Unit Code')
    qty_unit_cd = fields.Char(string='Quantity Country Code')
    remark = fields.Text(string='Remark')
    status = fields.Selection([
        ('draft', 'Draft'),
        ('rejected', 'Rejected'),
        ('partial', 'Partial'),
        ('confirmed', 'Confirmed')
    ], string='Status', default='draft')
    item_list = fields.One2many('import.item', 'import_id', string='Items')
    fetched = fields.Boolean(string='Fetched', default=False)
    fetch_selection = fields.Selection(
        selection='_compute_fetch_selection',
        string='Fetch Selection',
        required=False,

        help="Select an item from the fetched data."
    )
    classification = fields.Many2one(
        'zra.item.data',
        string='Item Classification',
        required=False
    )
    item_cls_cd = fields.Char(string='Item Classification Code', readonly=True, store=True)
    item_cls_lvl = fields.Integer(string='Item Classification Level', readonly=True, store=True)
    tax_ty_cd = fields.Char(string='Tax Type Code', readonly=True, store=True)
    mjr_tg_yn = fields.Char(string='Major Target', readonly=True, store=True)
    use_yn = fields.Char(string='Use', readonly=True, store=True)

    def values(self):
        print('item name', self.item_nm)

    @api.onchange('classification')
    def _onchange_classification(self):
        if self.classification:
            self.item_cls_cd = self.classification.itemClsCd
            self.item_cls_lvl = self.classification.itemClsLvl
            self.tax_ty_cd = self.classification.taxTyCd
            self.mjr_tg_yn = self.classification.mjrTgYn
            self.use_yn = self.classification.useYn
        else:
            self.item_cls_cd = False
            self.item_cls_lvl = False
            self.tax_ty_cd = False
            self.mjr_tg_yn = False
            self.use_yn = False

    def _fetch_import_items_data(self):
        global compute_fetch_selection_counter, fetch_import_data_counter
        global compute_fetch_selection_cache, compute_fetch_selection_last_request
        company = self.env.company
        # config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        company_id = self.env.company.id
        company_id = self.env.company.id
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.import_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "lastReqDt": "20240105210300"
        }

        # Check if cache is empty or last request date has changed
        if compute_fetch_selection_cache is None or compute_fetch_selection_last_request != payload['lastReqDt']:
            compute_fetch_selection_counter += 1
            fetch_import_data_counter += 1
            print('Compute Fetch Selection Endpoint Hit Count:', compute_fetch_selection_counter)
            print('Fetch Import Data Endpoint Hit Count:', fetch_import_data_counter)

            try:
                response = requests.post(api_url, json=payload)
                response.raise_for_status()
                result = response.json()

                if result.get('resultCd') != '000':
                    return []

                item_list = result.get('data', {}).get('itemList', [])
                compute_fetch_selection_cache = item_list
                compute_fetch_selection_last_request = payload['lastReqDt']
            except requests.exceptions.RequestException as e:
                _logger.error('Error fetching fetch options:', e)
                return []

        return compute_fetch_selection_cache

    def _compute_fetch_selection(self):
        item_list = self._fetch_import_items_data()

        if not item_list:
            return []

        selection_data = [
            (
                f"{item['taskCd']}_{item['itemSeq']}",
                f"{item['itemNm']} - {item['taskCd']} - {item['orgnNatCd']}"
            )
            for item in item_list
        ]
        return selection_data
    @api.onchange('fetch_selection')
    def _onchange_fetch_selection(self):
        if self.fetch_selection:
            self.fetch_import_data()

    def fetch_import_data(self):
        item_list = self._fetch_import_items_data()

        if not self.fetch_selection:
            raise UserError(_('No selection made.'))

        task_cd, item_seq = self.fetch_selection.split('_')

        selected_item = next(
            (item for item in item_list if str(item['taskCd']) == task_cd and str(item['itemSeq']) == item_seq),
            None
        )

        if not selected_item:
            raise UserError(_('Selected item not found in the fetched data.'))

        # Create or update the selected item
        self.create_or_update_import_data(selected_item)

        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Data',
            'res_model': 'import.data',
            'view_mode': 'tree,form',
            'views': [
                (self.env.ref('zra_smart_invoice.view_import_data_tree').id, 'tree'),
                (self.env.ref('zra_smart_invoice.view_import_data_form').id, 'form')
            ],
            'target': 'current',
        }

    def print_endpoint_hits(self):
        print('Compute Fetch Selection Endpoint Hit Count:', compute_fetch_selection_counter)
        print('Fetch Import Data Endpoint Hit Count:', fetch_import_data_counter)

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

    def fetch_existing_quantities_Full_confirm(self):
        product_quantities = {}
        for item in self.item_list:
            product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
            if product_template:
                product = self.env['product.product'].search([('product_tmpl_id', '=', product_template.id)], limit=1)
                if product:
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id', '=', self.env.ref('stock.stock_location_stock').id)
                    ], limit=1)
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

    def create_or_update_import_data(self, item):
        if not item.get('taskCd') or not item.get('dclNo'):
            _logger.warning('Skipped creation of record due to missing taskCd or dclNo')
            return

        existing_record = self.search([('task_cd', '=', item.get('taskCd')), ('dcl_no', '=', item.get('dclNo'))])
        item_values = {
            'item_seq': item.get('itemSeq'),
            'hs_cd': item.get('hsCd'),
            'item_nm': item.get('itemNm'),
            'pkg': item.get('pkg'),
            'pkg_unit_cd': item.get('pkgUnitCd'),
            'orgn_nat_cd': item.get('orgnNatCd'),  # Ensure this is correctly fetched
            'qty': item.get('qty'),
            'fetched_qty': item.get('qty'),
            'qty_unit_cd': item.get('qtyUnitCd'),
            'tot_wt': item.get('totWt'),
            'net_wt': item.get('netWt'),
            'agnt_nm': item.get('agntNm'),
            'invc_fcur_amt': item.get('invcFcurAmt')
        }

        if existing_record:
            # Update existing record
            existing_record.write({
                'task_cd': item.get('taskCd'),
                'dcl_de': self._parse_date(item.get('dclDe')),
                'dcl_no': item.get('dclNo'),
                'tot_wt': item.get('totWt'),
                'net_wt': item.get('netWt'),
                'agnt_nm': item.get('agntNm'),
                'invc_fcur_amt': item.get('invcFcurAmt'),
                'invc_fcur_cd': item.get('invcFcurCd'),
                'invc_fcur_excrt': item.get('invcFcurExcrt'),
                'remark': item.get('remark'),
                'status': 'draft',
                'fetched': True,
            })

            # Update or create item in item_list
            existing_item = existing_record.item_list.filtered(lambda x: x.item_seq == item.get('itemSeq'))
            if existing_item:
                existing_item.write(item_values)
            else:
                existing_record.write({'item_list': [(0, 0, item_values)]})

        else:
            # Create new record
            vals = {
                'task_cd': item.get('taskCd'),
                'dcl_de': self._parse_date(item.get('dclDe')),
                'dcl_no': item.get('dclNo'),
                'tot_wt': item.get('totWt'),
                'item_nm': item.get('itemNm'),
                'net_wt': item.get('netWt'),
                'agnt_nm': item.get('agntNm'),
                'orgn_nat_cd': item.get('orgnNatCd'),
                'invc_fcur_amt': item.get('invcFcurAmt'),
                'invc_fcur_cd': item.get('invcFcurCd'),
                'invc_fcur_excrt': item.get('invcFcurExcrt'),
                'remark': item.get('remark'),
                'status': 'draft',
                'fetched': True,
                'item_list': [(0, 0, item_values)]
            }
            self.create(vals)

            import_data_instance = self.search(
                [('task_cd', '=', item.get('taskCd')), ('dcl_no', '=', item.get('dclNo'))])
            for item in import_data_instance.item_list:
                item.check_item_name()

    def _parse_date(self, date_str):
        try:
            return datetime.strptime(date_str, '%Y%m%d').date()
        except ValueError:
            return False

    def refresh_list(self):

        global compute_fetch_selection_cache, compute_fetch_selection_last_request

        compute_fetch_selection_cache = None
        compute_fetch_selection_last_request = None
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_confirm_import(self):

        global compute_fetch_selection_cache, compute_fetch_selection_last_request

        compute_fetch_selection_cache = None
        compute_fetch_selection_last_request = None

        self.ensure_one()

        print('Cache reset after confirming import')

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

        # Fetch existing quantities
        product_quantities = self.fetch_existing_quantities()

        for item in self.item_list:
            confirmed_qty = item.qty
            fetched_qty = item.fetched_qty
            rejected_qty = fetched_qty - confirmed_qty

            existing_qty = product_quantities.get(item.item_nm, 0)

            total_confirmed_qty = existing_qty + confirmed_qty

            print(
                f"Fetched: {fetched_qty}, Confirmed: {confirmed_qty}, Rejected: {rejected_qty}, Existing: {existing_qty}, Total Confirmed: {total_confirmed_qty}")

            if confirmed_qty == 0:
                rejected_items.append(item)
                io_rejected_items.append(item)
            else:
                product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
                if product_template:
                    item_cd = product_template.item_Cd
                else:
                    item_cd = False

                confirmed_items.append(item)
                io_confirmed_items.append(item)
                confirmed_stock_items.append({
                    "itemCd": item.item_cd or item_cd,
                    "rsdQty": total_confirmed_qty
                })
                confirmed_io_items.append({
                    "itemSeq": item.item_seq,
                    "itemCd": item.item_cd or item_cd,
                    "itemClsCd": item.item_cls_cd,
                    "itemNm": item.item_nm,
                    "bcd": None,
                    "pkgUnitCd": item.pkg_unit_cd,
                    "pkg": item.pkg,
                    "qtyUnitCd": item.qty_unit_cd,
                    "qty": confirmed_qty,
                    "itemExprDt": None,
                    "prc": item.invc_fcur_amt,
                    "splyAmt": item.qty * item.invc_fcur_amt,
                    "totDcAmt": 0,
                    "taxblAmt": item.qty * item.invc_fcur_amt,
                    "vatCatCd": 'D',
                    "iplCatCd": None,
                    "tlCatCd": None,
                    "exciseTxCatCd": None,
                    "vatAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "iplAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "tlAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "exciseTxAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "taxAmt": 16,
                    "totAmt": item.qty * item.invc_fcur_amt
                })

                all_rejected = False

            if rejected_qty > 0:
                product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
                if product_template:
                    item_cd = product_template.item_Cd
                else:
                    item_cd = False

                rejected_items.append(item)
                io_rejected_items.append(item)
                rejected_stock_items.append({
                    "itemCd": item.item_cd or item_cd,
                    "rsdQty": rejected_qty
                })

                rejected_io_items.append({
                    "itemSeq": item.item_seq,
                    "itemCd": item.item_cd or item_cd,
                    "itemClsCd": item.item_cls_cd,
                    "itemNm": item.item_nm,
                    "bcd": None,
                    "pkgUnitCd": item.pkg_unit_cd,
                    "pkg": item.pkg,
                    "qtyUnitCd": item.qty_unit_cd,
                    "qty": rejected_qty,
                    "itemExprDt": None,
                    "prc": item.invc_fcur_amt,
                    "splyAmt": item.qty * item.invc_fcur_amt,
                    "totDcAmt": 0,
                    "taxblAmt": item.qty * item.invc_fcur_amt,
                    "vatCatCd": 'D',
                    "iplCatCd": None,
                    "tlCatCd": None,
                    "exciseTxCatCd": None,
                    "vatAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "iplAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "tlAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "exciseTxAmt": item.qty * item.invc_fcur_amt * 0.16,
                    "taxAmt": 16,
                    "totAmt": item.qty * item.invc_fcur_amt
                })

                all_confirmed = False

        if all_confirmed:
            print('All items are confirmed.')
            self.update_import_items_full_confirmation()
            self.save_stock_items_full_confirmed()
            self.save_stock_master_full_confirmed()
            self.status = 'confirmed'
        elif all_rejected:
            print('All items are rejected.')
            self.reject_import_items_full_confirmation()
            self.status = 'rejected'
        else:
            print('Partial confirmation.')
            self.update_import_items()

            # print("Saving confirmed items with stock master payload:")
            self.save_stock_items(confirmed_io_items)

            # print("Saving confirmed items with stock master payload:")
            self.save_stock_master(confirmed_stock_items)

            self.reject_import_items()
            # print("Saving rejected items with stock master payload:")
            # self.save_stock_items(rejected_io_items)

            # print("Saving rejected items with stock master payload:")
            # self.save_stock_master(rejected_stock_items)

            self.status = 'partial'

        self.create_or_update_products()

        # return {
        #     'type': 'ir.actions.client',
        #     'tag': 'display_notification',
        #     'params': {
        #         'title': _('Success'),
        #         'message': _('Import Validated Successfully'),
        #         'sticky': False,
        #     }
        # }

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'import.data',
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
                'name': product_name,
                'type': 'product',
                'list_price': item.invc_fcur_amt,
                'standard_price': item.invc_fcur_amt,
                'weight': item.net_wt,
                'packaging_unit_cd': item.pkg_unit_cd,
                'quantity_unit_cd': item.qty_unit_cd,
                'use_yn': item.use_yn or 'Y',
                'item_cls_cd': item.item_cls_cd,
                'item_Cd': item.item_cd,
                'cd': item.orgn_nat_cd,
            }

            if existing_template:
                # Update existing product template
                existing_template.write(template_values)
            else:
                # Create new product template
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
            else:
                stock_quant_model.create({
                    'product_id': product_variant.id,
                    'location_id': stock_location.id,
                    'quantity': item.qty,
                })

        # Optionally, commit the transaction if necessary
        self.env.cr.commit()

    def confirm_import(self):
        self.write({'status': 'confirmed'})

    def update_import_items(self):
        if not self.item_list:
            raise UserError(_('No items to import.'))

        confirmed_qty = sum(item.qty for item in self.item_list)
        fetched_qty = sum(item.fetched_qty for item in self.item_list)
        rejected_qty = fetched_qty - confirmed_qty
        print('rejected', rejected_qty)

        for item in self.item_list:
            product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
            if product_template:
                item_cd = product_template.item_Cd
                class_cd = product_template.item_cls_cd
            else:
                item_cd = False
                class_cd = False
        company = self.env.company
        company_id = self.env.company.id
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url =  config_settings.import_update_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "taskCd": self.task_cd,
            "dclDe": self.dcl_de.strftime('%Y%m%d'),
            "importItemList": [{
                "itemSeq": item.item_seq,
                "hsCd": item.hs_cd,
                "itemClsCd": item.item_cls_cd or class_cd,
                "itemCd": item.item_cd or item_cd,
                "imptItemSttsCd": "3",
                "remark": item.remark or "Imports",
                "modrNm": self.create_uid.name,
                "modrId": self.create_uid.id,
            } for item in self.item_list]
        }
        print(json.dumps(payload, indent=4))
        response = requests.post(api_url, json=payload)
        if response.status_code != 200:
            raise UserError(_('Failed to update import items: HTTP %s') % response.status_code)
        _logger.info('Import items updated: %s', response.json())
        print('Update saved successfully:', response.json())

    def update_import_items_full_confirmation(self):
        company = self.env.company
        if not self.item_list:
            raise UserError(_('No items to import.'))

        confirmed_qty = sum(item.qty for item in self.item_list)
        fetched_qty = sum(item.fetched_qty for item in self.item_list)
        rejected_qty = fetched_qty - confirmed_qty
        print('rejected', rejected_qty)

        for item in self.item_list:
            product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
            if product_template:
                item_cd = product_template.item_Cd
                class_cd = product_template.item_cls_cd
            else:
                item_cd = False
                class_cd = False

        company_id = self.env.company.id
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.import_update_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "taskCd": self.task_cd,
            "dclDe": self.dcl_de.strftime('%Y%m%d'),
            "importItemList": [{
                "itemSeq": item.item_seq,
                "hsCd": item.hs_cd,
                "itemClsCd": item.item_cls_cd or class_cd,
                "itemCd": item.item_cd or item_cd,
                "imptItemSttsCd": "3",
                "remark": item.remark or "remark",
                "modrNm": self.create_uid.name,
                "modrId": self.create_uid.id,
            } for item in self.item_list]
        }
        print(payload)
        response = requests.post(api_url, json=payload)
        if response.status_code != 200:
            raise UserError(_('Failed to update import items: HTTP %s') % response.status_code)
        _logger.info('Import items updated: %s', response.json())
        print('Update saved successfully:', response.json())

    def reject_import_items(self, item=None):
        company = self.env.company
        if not self.item_list:
            raise UserError(_('No items to import.'))

        confirmed_qty = sum(item.qty for item in self.item_list)
        fetched_qty = sum(item.fetched_qty for item in self.item_list)
        rejected_qty = fetched_qty - confirmed_qty

        for item in self.item_list:
            product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
            if product_template:
                item_cd = product_template.item_Cd
                class_cd = product_template.item_cls_cd
            else:
                item_cd = False
                class_cd = False

        company_id = self.env.company.id
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.import_update_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "taskCd": self.task_cd,
            "dclDe": self.dcl_de.strftime('%Y%m%d'),
            "importItemList": [{
                "itemSeq": item.item_seq,
                "hsCd": item.hs_cd,
                "itemClsCd": item.item_cls_cd or class_cd,
                "itemCd": item.item_cd or item_cd,
                "imptItemSttsCd": "4",
                "remark": item.remark or "",
                "modrNm": self.create_uid.name,
                "modrId": self.create_uid.id,
            } for item in self.item_list if item.qty > item.confirmed_qty]
        }

        # print("Payload:")
        print(json.dumps(payload, indent=4))  # Print the payload in JSON format

        response = requests.post(api_url, json=payload)
        if response.status_code != 200:
            raise UserError(_('Failed to update import items: HTTP %s') % response.status_code)
        _logger.info('Import items updated: %s', response.json())
        print('Rejected saved successfully:', response.json())

    def reject_import_items_full_confirmation(self, item=None):
        company = self.env.company
        if not self.item_list:
            raise UserError(_('No items to import.'))

        confirmed_qty = sum(item.qty for item in self.item_list)
        fetched_qty = sum(item.fetched_qty for item in self.item_list)
        rejected_qty = fetched_qty - confirmed_qty

        for item in self.item_list:
            product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
            if product_template:
                item_cd = product_template.item_Cd
                class_cd = product_template.item_cls_cd
            else:
                item_cd = False
                class_cd = False

        company_id = self.env.company.id
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.import_update_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "taskCd": self.task_cd,
            "dclDe": self.dcl_de.strftime('%Y%m%d'),
            "importItemList": [{
                "itemSeq": item.item_seq,
                "hsCd": item.hs_cd,
                "itemClsCd": item.item_cls_cd or class_cd,
                "itemCd": item.item_cd or item_cd,
                "imptItemSttsCd": "4",
                "remark": item.remark or "",
                "modrNm": self.create_uid.name,
                "modrId": self.create_uid.id,
            } for item in self.item_list]
        }

        # print("Payload:")
        # print(json.dumps(payload, indent=4))  # Print the payload in JSON format

        response = requests.post(api_url, json=payload)
        if response.status_code != 200:
            raise UserError(_('Failed to update import items: HTTP %s') % response.status_code)
        _logger.info('Import items updated: %s', response.json())
        print('Rejected saved successfully:', response.json())

    def save_stock_items(self, imp_qty):
        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.stock_io_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": None,
            "custNm": None,
            "custBhfId": "000",
            "sarTyCd": "01",
            "ocrnDt": fields.Date.today().strftime('%Y%m%d'),
            "totItemCnt": len(self.item_list),
            "totTaxblAmt": sum(item.qty * item.invc_fcur_amt for item in self.item_list),
            "totTaxAmt": sum(item.qty * item.invc_fcur_amt * 0.16 for item in self.item_list),
            "totAmt": sum(item.qty * item.invc_fcur_amt for item in self.item_list),
            "remark": self.remark,
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "itemList": imp_qty,
        }

        print("Save Stock Items Payload:")
        # print(payload)

        response = requests.post(api_url, json=payload)
        if response.status_code != 200:
            print(f"Response Status Code: {response.status_code}")
            # print(f"Response Content: {response.content}")
            raise UserError(_('Failed to save stock items: HTTP %s') % response.status_code)
        _logger.info('Stock items saved: %s', response.json())
        print('save stock saved successfully:', response.json())

    def save_stock_master(self, imp_qty):
        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.stock_master_endpoint
        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "stockItemList": imp_qty,
        }

        # print("Save Stock Master Payload:")
        print(payload)

        response = requests.post(api_url, json=payload)

        if response.status_code != 200:
            raise UserError(_('Failed to save stock master: HTTP %s') % response.status_code)
        _logger.info('Stock master saved: %s', response.json())
        print('save master saved successfully:', response.json())

    def save_stock_items_full_confirmed(self):
        company = self.env.company
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.stock_io_endpoint

        # Fetch existing quantities
        product_quantities = self.fetch_existing_quantities()

        payload = {
            "tpin": company.tpin,
            "bhfId": company.bhf_id,
            "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
            "orgSarNo": 0,
            "regTyCd": "M",
            "custTpin": None,
            "custNm": None,
            "custBhfId": "000",
            "sarTyCd": "01",
            "ocrnDt": fields.Date.today().strftime('%Y%m%d'),
            "totItemCnt": len(self.item_list),
            "totTaxblAmt": sum(item.qty * item.invc_fcur_amt for item in self.item_list),
            "totTaxAmt": sum(item.qty * item.invc_fcur_amt * 0.16 for item in self.item_list),
            "totAmt": sum(item.qty * item.invc_fcur_amt for item in self.item_list),
            "remark": self.remark,
            "regrId": self.create_uid.id,
            "regrNm": self.create_uid.name,
            "modrNm": self.create_uid.name,
            "modrId": self.create_uid.id,
            "itemList": []
        }

        for item in self.item_list:
            confirmed_qty = item.qty
            existing_qty = product_quantities.get(item.item_nm, 0)

            # Search for product template based on item name
            product_template = self.env['product.template'].search([('name', '=', item.item_nm)], limit=1)
            if product_template:
                item_cd = product_template.item_Cd
            else:
                item_cd = False  # Set default value if product template not found

            payload["itemList"].append({
                "itemSeq": item.item_seq,
                "itemCd": item.item_cd or item_cd,
                "itemClsCd": item.item_cls_cd,
                "itemNm": item.item_nm,
                "bcd": None,
                "pkgUnitCd": item.pkg_unit_cd,
                "pkg": item.pkg,
                "qtyUnitCd": item.qty_unit_cd,
                "qty": item.qty,
                "itemExprDt": None,
                "prc": item.invc_fcur_amt,
                "splyAmt": item.qty * item.invc_fcur_amt,
                "totDcAmt": 0,
                "taxblAmt": item.qty * item.invc_fcur_amt,
                "vatCatCd": 'D',
                "iplCatCd": None,
                "tlCatCd": None,
                "exciseTxCatCd": None,
                "vatAmt": item.qty * item.invc_fcur_amt * 0.16,
                "iplAmt": item.qty * item.invc_fcur_amt * 0.16,
                "tlAmt": item.qty * item.invc_fcur_amt * 0.16,
                "exciseTxAmt": item.qty * item.invc_fcur_amt * 0.16,
                "taxAmt": 16,
                "totAmt": item.qty * item.invc_fcur_amt
            })

        # print("Save Stock Items Payload:")
        print(payload)

        # Send the request to save stock items
        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()
            _logger.info('Stock items saved successfully: %s', response.json())
            print('Save stock saved successfully:', response.json())
        except requests.exceptions.RequestException as e:
            _logger.error('Error saving stock items: %s', e)
            raise UserError(_('Failed to save stock items data.'))

    def save_stock_master_full_confirmed(self):
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        api_url = config_settings.stock_master_endpoint

        # Fetch existing quantities
        product_quantities = self.fetch_existing_quantities()
        company = self.env.company

        # Prepare the payload with updated quantities
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

        print("Save Stock Master Payload:")
        print(payload)

        # Send the request to save stock master
        try:
            response = requests.post(api_url, json=payload)
            response.raise_for_status()
            _logger.info('Stock master saved successfully: %s', response.json())
            print('Save master saved successfully:', response.json())
        except requests.exceptions.RequestException as e:
            _logger.error('Error saving stock master: %s', e)
            raise UserError(_('Failed to save stock master data.'))


class ImportItem(models.Model):
    _name = 'import.item'
    _description = 'Import Item'

    import_id = fields.Many2one('import.data', string='Import ID')
    item_seq = fields.Integer(string='Item Sequence')
    hs_cd = fields.Char(string='HS Code')
    item_nm = fields.Char(string='Item Name')
    confirmed_qty = fields.Float(string='Confirmed Quantity', default=0.0)
    pkg = fields.Integer(string='Package')
    pkg_unit_cd = fields.Char(string='Package Unit Code')
    qty = fields.Integer(string='Accepted Quantity')
    fetched_qty = fields.Integer(string='Received Quantity')
    qty_unit_cd = fields.Char(string='Quantity Unit Code')
    orgn_nat_cd = fields.Char(string="Original Country Code")
    expt_nat_cd = fields.Char(string="Expected Country Code")
    tot_wt = fields.Float(string='Total Weight')
    net_wt = fields.Float(string='Net Weight')
    agnt_nm = fields.Char(string='Agent Name')
    invc_fcur_amt = fields.Float(string='Invoice Foreign Currency Amount')
    remark = fields.Text(string='Remark')
    item_cd = fields.Char(string='Item Code')
    task_cd = fields.Char(string='Task Code')
    classification = fields.Many2one(
        'zra.item.data',
        string='Item Classification',
        required=False
    )
    item_cls_cd = fields.Char(string='Item Classification Code', readonly=False, store=True)
    item_cls_lvl = fields.Integer(string='Item Classification Level', readonly=True, store=True)
    tax_ty_cd = fields.Char(string='Tax Type Code', readonly=True, store=True)
    mjr_tg_yn = fields.Char(string='Major Target', readonly=True, store=True)
    use_yn = fields.Char(string='Use', readonly=True, store=True)
    _item_cd_options_array = []

    def check_product_exists(self):
        print(f"Checking product for item_nm: {self.item_nm}")
        if not self.item_nm:
            return False
        product = self.env['product.template'].search([('name', '=', self.item_nm)], limit=1)
        if product:
            return product.name
        return False

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

    def check_item_name(self):
        product_name = self.check_product_exists()
        if product_name:
            # Product exists, handle accordingly
            print(f"Product {product_name} exists.")
        else:
            # Product does not exist, handle accordingly
            print(f"Product with name {self.item_nm} does not exist.")

    @api.onchange('classification')
    def _onchange_classification(self):
        if self.classification:
            self.item_cls_cd = self.classification.itemClsCd
            self.item_cls_lvl = self.classification.itemClsLvl
            self.tax_ty_cd = self.classification.taxTyCd
            self.mjr_tg_yn = self.classification.mjrTgYn
            self.use_yn = self.classification.useYn
        else:
            self.item_cls_cd = False
            self.item_cls_lvl = False
            self.tax_ty_cd = False
            self.mjr_tg_yn = False
            self.use_yn = False

    @api.model
    def _find_product_name(self, item_name, item_cd):
        domain = [('name', '=', item_name)]
        if item_cd:
            domain.append(('item_Cd', '=', item_cd))
        product = self.env['product.template'].search(domain, limit=1)
        print('Code', product.item_Cd)
        return product.item_Cd if product else False

    # @api.onchange('item_nm')
    # def _onchange_item_nm(self):
    #     if self.item_nm:
    #         self.item_cd = self._get_item_cd_options()
    #
    # _sql_constraints = [
    #     ('uniq_name_item_cd', 'unique(name, item_cd)', 'Name and Item Code must be unique.')
    # ]

    @api.model
    def _find_product_classification(self, item_name, item_cd):
        domain = [('name', '=', item_name)]
        if item_cd:
            domain.append(('item_Cd', '=', item_cd))
        product = self.env['product.template'].search(domain, limit=1)
        return product.classification if product else False

    @api.model
    def create(self, vals):
        if not vals.get('classification'):
            classification = self._find_product_classification(vals.get('item_nm'), vals.get('item_cd'))
            if classification:
                vals['classification'] = classification.id

        if 'classification' in vals:
            classification = self.env['zra.item.data'].browse(vals['classification'])
            if classification.exists():
                vals.update({
                    'item_cls_cd': classification.itemClsCd,
                    'item_cls_lvl': classification.itemClsLvl,
                    'tax_ty_cd': classification.taxTyCd,
                    'mjr_tg_yn': classification.mjrTgYn,
                    'use_yn': classification.useYn
                })

        res = super(ImportItem, self).create(vals)
        return res

    def write(self, vals):
        if not vals.get('classification'):
            classification = self._find_product_classification(self.item_nm, self.item_cd)
            if classification:
                vals['classification'] = classification.id

        if 'classification' in vals:
            classification = self.env['zra.item.data'].browse(vals['classification'])
            if classification.exists():
                vals.update({
                    'item_cls_cd': classification.itemClsCd,
                    'item_cls_lvl': classification.itemClsLvl,
                    'tax_ty_cd': classification.taxTyCd,
                    'mjr_tg_yn': classification.mjrTgYn,
                    'use_yn': classification.useYn
                })

        res = super(ImportItem, self).write(vals)
        return res

    @api.constrains('qty')
    def _check_qty(self):
        for record in self:
            if record.qty < 0:
                raise ValidationError("Accepted Quantity cannot be less than 0.")
            if record.qty > record.fetched_qty:
                raise ValidationError("Accepted Quantity cannot be greater than Received Quantity.")

    @api.depends('import_id.item_list')
    def _compute_confirmed_qty(self):
        for item in self:
            item.confirmed_qty = item.qty

    def generate_item_code(self):
        # Check if the item code has already been generated for this product
        existing_item = self.env['product.template'].search([
            ('name', '=', self.item_nm),
            ('item_Cd', 'ilike', self.item_nm[:2] + self.pkg_unit_cd[:2] + self.qty_unit_cd[:2])
        ], limit=1)
        if existing_item:
            self.item_cd = existing_item.item_Cd
            return {
                'type': 'ir.actions.act_window',
                'view_mode': 'form',
                'res_model': 'import.data',
                'res_id': self.id,
                'target': 'current',
                'flags': {'form_view_initial_mode': 'edit'},
                'context': self.env.context,
            }

        # Locking mechanism to prevent race conditions
        sequence = self.env['item.code.sequence'].sudo().search([], limit=1)
        if not sequence:
            sequence = self.env['item.code.sequence'].sudo().create({})

        next_number = sequence.next_number
        sequence.sudo().write({'next_number': next_number + 1})
        next_number_str = str(next_number).zfill(7)
        item_code = f"{self.item_nm[:2]}{self.pkg_unit_cd[:2]}{self.qty_unit_cd[:2]}{next_number_str}"

        # Ensure the item code is added to selection options
        self.env['product.template'].create({
            'name': self.item_nm,
            'item_Cd': item_code,
        })

        # Add the generated item code to the selection options array
        type(self)._item_cd_options_array.append((item_code, item_code))
        self.item_cd = item_code

        return {
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'import.data',
            'res_id': self.id,
            'target': 'current',
            'flags': {'form_view_initial_mode': 'edit'},
            'context': self.env.context,
        }
