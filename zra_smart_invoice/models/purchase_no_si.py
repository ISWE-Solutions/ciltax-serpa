from odoo import models, api
import logging
import requests
import json
import re
from datetime import datetime
_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def get_tax_description(self, taxes):
        if taxes:
            return ", ".join(tax.description or "" for tax in taxes)
        return ""

    def button_validate(self):
        _logger.info('Entering button_validate method.')

        res = super(StockPicking, self).button_validate()

        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)

        for picking in self:
            _logger.info(f'Processing picking with type: {picking.picking_type_id.code}')

            moves = picking.move_ids_without_package

            total_taxable_amount = 0
            total_tax_amount = 0
            total_amount = 0

            # Construct itemList once
            item_list = []
            for idx, move in enumerate(moves):
                product = move.product_id
                product_template = product.product_tmpl_id

                _logger.info(f'Processing move for product: {product.display_name}')

                taxes = move.sale_line_id.tax_id if move.sale_line_id else move.purchase_line_id.taxes_id
                product_price = product_template.standard_price  # default to standard price
                supplier_info = self.env['product.supplierinfo'].search([('product_tmpl_id', '=', product_template.id)],
                                                                        limit=1)
                if supplier_info:
                    product_price = supplier_info.price

                qty = move.product_uom_qty
                price = product_price
                supply_amount = qty * price

                # tax_description = taxes[0].description if taxes else 'A'
                tax_description =self.get_tax_description(move.purchase_line_id.taxes_id)
                tax_rate = taxes[0].amount / 100 if taxes else 0.16  # Default to 16% if no taxes

                tax_amount = supply_amount * tax_rate
                total_item_amount = supply_amount + tax_amount

                total_taxable_amount += supply_amount
                total_tax_amount += tax_amount
                total_amount += total_item_amount

                item_list.append({
                    "itemSeq": idx + 1,
                    "itemCd": product_template.item_Cd  or str(move.product_id.id),
                    "itemClsCd": move.product_id.product_tmpl_id.item_cls_cd,
                    "itemNm": move.product_id.display_name,
                    "bcd": "",
                    "spplrItemClsCd": None,
                    "spplrItemCd": None,
                    "spplrItemNm": None,
                    "pkgUnitCd": product_template.packaging_unit_cd,
                    "pkg": qty,
                    "qtyUnitCd": product_template.quantity_unit_cd,
                    "qty": qty,
                    "prc": price,
                    "splyAmt": supply_amount,
                    "totDcAmt": 0,
                    "dcRt": 0,
                    "dcAmt": 0,
                    "vatCatCd": tax_description,
                    "iplCatCd": None,
                    "tlCatCd": None,
                    "exciseTxCatCd": None,
                    "taxAmt": round(tax_amount, 2),
                    "taxblAmt": round(supply_amount, 2),
                    "totAmt": round(total_item_amount, 2),
                    "itemExprDt": None
                })

                # Calculate the updated stock quantity
                stock_quant = self.env['stock.quant'].search(
                    [('product_id', '=', product.id), ('location_id', '=', picking.location_dest_id.id)], limit=1)
                if not stock_quant:
                    current_stock_qty = 0
                else:
                    current_stock_qty = stock_quant.quantity

                # Adjust stock quantity based on operation type
                if picking.picking_type_id.code == 'incoming':
                    updated_stock_qty = current_stock_qty
                elif picking.picking_type_id.code == 'outgoing':
                    updated_stock_qty = stock_quant.quantity

            company = self.env.company

            if picking.picking_type_id.code == 'incoming':
                payload_purchase = {
                    "tpin": company.tpin,
                    "bhfId": company.bhf_id,
                    "invcNo": re.search(r'\d+', picking.name).group(),
                    "orgInvcNo": 0,
                    "spplrTpin": picking.partner_id.tpin or None,
                    "spplrBhfId": "000",
                    "spplrNm": picking.partner_id.name,
                    "spplrInvcNo": None,
                    "regTyCd": "M",
                    "pchsTyCd": "N",
                    "rcptTyCd": "P",
                    "pmtTyCd": "01",
                    "pchsSttsCd": "02",
                    "cfmDt": picking.scheduled_date.strftime(
                        "%Y%m%d%H%M%S") if picking.scheduled_date else "20240502210300",
                    "pchsDt": picking.scheduled_date.strftime("%Y%m%d") if picking.scheduled_date else "20240502",
                    "cnclReqDt": "",
                    "cnclDt": "",
                    "rfdDt": "",
                    "totItemCnt": len(moves),
                    "totTaxblAmt": round(total_taxable_amount, 2),
                    "totTaxAmt": round(total_tax_amount, 2),
                    "totAmt": round(total_amount, 2),
                    "remark": picking.note or "",
                    "regrNm": picking.write_uid.name,
                    "regrId": picking.write_uid.id,
                    "modrNm": picking.write_uid.name,
                    "modrId": picking.write_uid.id,
                    "itemList": item_list
                }

                _logger.info('Payload being sent:', json.dumps(payload_purchase, indent=4))

                try:
                    response = requests.post(config_settings.purchase_endpoint, json=payload_purchase)
                    response.raise_for_status()
                    result_msg_purchase = response.json().get('resultMsg', 'No result message returned')

                    picking.message_post(
                        body="API Response Item Purchase: %s, \nProduct Name: %s" % (
                            result_msg_purchase, move.product_id.display_name),
                        subtype_id=self.env.ref('mail.mt_note').id
                    )

                    _logger.info(f'API Purchase Response: {result_msg_purchase}')
                   
                except requests.exceptions.RequestException as e:
                    _logger.error(f'API request failed: {e}')
                    

                payload_stock_master = {
                    "tpin": company.tpin,
                    "bhfId": company.bhf_id,
                    "regrId": picking.create_uid.name or "Admin",
                    "regrNm": picking.create_uid.name or "Admin",
                    "modrNm": picking.write_uid.name or "Admin",
                    "modrId": picking.write_uid.name or "Admin",
                    "stockItemList": [
                        {
                            "itemCd": product_template.item_Cd or product.default_code or product.id,
                            "rsdQty": updated_stock_qty  # Pass the updated stock quantity here
                        }
                    ]
                }

                _logger.info('Payload being sent:', json.dumps(payload_stock_master, indent=4))

                try:
                    response = requests.post(config_settings.stock_master_endpoint,
                                             json=payload_stock_master)
                    response.raise_for_status()
                    result_msg_stock_master = response.json().get('resultMsg', 'No result message returned')

                    picking.message_post(
                        body="Save Stock Master API Response: %s, \nProduct Name: %s" % (
                            result_msg_stock_master, product.display_name),
                        subtype_id=self.env.ref('mail.mt_note').id
                    )

                    _logger.info(f'API Stock Master Response: {result_msg_stock_master}')
              
                except requests.exceptions.RequestException as e:
                    _logger.error(f'API request failed: {e}')

            # elif picking.picking_type_id.code == 'outgoing':
                payload_new_endpoint = {
                    "tpin": company.tpin,
                    "bhfId": company.bhf_id,
                    "sarNo": int(datetime.now().strftime('%m%d%H%M%S')),
                    "orgSarNo": 0,
                    "regTyCd": "M",
                    "custTpin": picking.partner_id.tpin or None,
                    "custNm": picking.partner_id.name or None,
                    "custBhfId": "000",
                    "sarTyCd": "02",
                    "ocrnDt": picking.scheduled_date.strftime("%Y%m%d") if picking.scheduled_date else "20200126",
                    "totItemCnt": len(moves),
                    "totTaxblAmt": round(total_taxable_amount, 2),
                    "totTaxAmt": round(total_tax_amount, 2),
                    "totAmt": round(total_amount, 2),
                    "remark": picking.note or "purchase order",
                    "regrId": picking.create_uid.name,
                    "regrNm": picking.create_uid.name,
                    "modrNm": picking.write_uid.name,
                    "modrId": picking.write_uid.name,
                    "itemList": item_list
                }

                _logger.info('Payload being sent:', json.dumps(payload_new_endpoint, indent=4))

                try:
                    response = requests.post(config_settings.stock_io_endpoint, json=payload_new_endpoint)
                    response.raise_for_status()
                    result_msg_new_endpoint = response.json().get('resultMsg', 'No result message returned')

                    picking.message_post(
                        body="Save Stock API Response New Endpoint: %s, \nProduct Name: %s" % (
                            result_msg_new_endpoint, move.product_id.display_name),
                        subtype_id=self.env.ref('mail.mt_note').id
                    )
                    _logger.info(f'API New Endpoint Response: {result_msg_new_endpoint}')
                except requests.exceptions.RequestException as e:
                    _logger.error(f'API request failed: {e}')

            _logger.info(f'Message posted for product: {product.display_name}')

        _logger.info('Exiting button_validate method.')

        return res
