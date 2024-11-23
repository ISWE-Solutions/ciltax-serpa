from odoo import models, fields, api
import requests
import json
from odoo.exceptions import UserError
from datetime import datetime


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    def action_validate(self):
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        for record in self:
            print("Function action_validate invoked")
            res = super(StockScrap, record).action_validate()

            # Ensure the product_id field exists and is not empty
            if not record.product_id:
                raise UserError("No product found for this scrap record.")

            product = record.product_id
            product_template = product.product_tmpl_id

            # Calculate the new quantity after scrap
            existing_qty = product.qty_available
            new_qty = existing_qty - record.scrap_qty

            print('existing', existing_qty)
            print('scrap', record.scrap_qty)
            print('new', new_qty)

            # Get VAT category code and amount from taxes
            vatCatCd = ""
            vatAmt = 0
            if product_template.taxes_id:
                vat_tax = product_template.taxes_id[0]
                vatCatCd = vat_tax.description or ""
                vatAmt = vat_tax.amount / 100 * product.lst_price

            # Prepare the data for the first endpoint
            company = self.env.company
            save_stock_items_payload = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "sarNo": 1,
                "orgSarNo": 0,
                "regTyCd": "M",
                "custTpin": None,
                "custNm": None,
                "custBhfId": "000",
                "sarTyCd": "15",
                "ocrnDt": fields.Date.today().strftime('%Y%m%d'),
                "totItemCnt": 1,
                "totTaxblAmt": product.lst_price,
                "totTaxAmt": vatAmt,
                "totAmt": product.lst_price + vatAmt,
                "remark": 'Scrap product',
                "regrId": self.env.user.id,
                "regrNm": self.env.user.name,
                "modrNm": self.env.user.name,
                "modrId": self.env.user.id,
                "itemList": []
            }

            item = {
                "itemSeq": record.id,
                "itemCd": product_template.item_Cd,
                "itemClsCd": product.categ_id.name if product.categ_id else "",
                "itemNm": product.name,
                "bcd": product.barcode,
                "pkgUnitCd": product_template.packaging_unit_cd,
                "pkg": 10,  # Adjust as needed
                "qtyUnitCd": product_template.quantity_unit_cd,
                "qty": record.scrap_qty,
                "itemExprDt": product.expiration_date if hasattr(product, 'expiration_date') else None,
                "prc": product.lst_price,
                "splyAmt": product.lst_price,
                "totDcAmt": 0,
                "taxblAmt": product.lst_price,
                "vatCatCd": vatCatCd,
                "iplCatCd": "IPL1",  # Adjust as needed
                "tlCatCd": "TL",  # Adjust as needed
                "exciseTxCatCd": "EXEEG",  # Adjust as needed
                "vatAmt": vatAmt,
                "iplAmt": vatAmt,  # Adjust as needed
                "tlAmt": vatAmt,  # Adjust as needed
                "exciseTxAmt": vatAmt,  # Adjust as needed
                "taxAmt": vatAmt,  # Adjust as needed
                "totAmt": product.lst_price + vatAmt
            }
            save_stock_items_payload['itemList'].append(item)
            print("Payload for saveStockMaster:", json.dumps(save_stock_items_payload, indent=4))
            # Send the request to the first endpoint
            headers = {'Content-Type': 'application/json'}
            response = requests.post(config_settings.stock_io_endpoint,
                                     data=json.dumps(save_stock_items_payload),
                                     headers=headers)
            print(f"First endpoint response status: {response.status_code}")
            print(f"First endpoint response content: {response.text}")

            if response.status_code != 200:
                raise UserError('Failed to send data to the first endpoint.')

            # Prepare the data for the second endpoint
            save_stock_master_payload = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "regrId": self.env.user.id,  # Use current user id
                "regrNm": self.env.user.name,  # Use current user name
                "modrNm": self.env.user.name,  # Use current user name
                "modrId": self.env.user.id,  # Use current user id
                "stockItemList": []
            }

            item = {
                "itemCd": product_template.item_Cd,
                "rsdQty": new_qty + record.scrap_qty
            }
            save_stock_master_payload['stockItemList'].append(item)
            print("Payload for saveStockMaster:", json.dumps(save_stock_master_payload, indent=4))
            # Send the request to the second endpoint
            response = requests.post(config_settings.stock_master_endpoint,
                                     data=json.dumps(save_stock_master_payload),
                                     headers=headers)
            print(f"Second endpoint response status: {response.status_code}")
            print(f"Second endpoint response content: {response.text}")

            if response.status_code != 200:
                raise UserError('Failed to send data to the second endpoint.')

        return res
