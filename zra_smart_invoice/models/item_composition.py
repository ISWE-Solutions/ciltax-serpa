from odoo import models, fields, api
import requests
import json
import logging

_logger = logging.getLogger(__name__)


class MrpBom(models.Model):
    _inherit = 'mrp.bom'

    @api.model
    def create(self, vals):
        print("Creating BOM with values:", vals)
        _logger.info("Creating BOM with values: %s", vals)

        # Fetch product_id from product_tmpl_id if not set
        if not vals.get('product_id') and vals.get('product_tmpl_id'):
            product_template = self.env['product.template'].browse(vals['product_tmpl_id'])
            if product_template:
                vals['product_id'] = product_template.product_variant_id.id

        record = super(MrpBom, self).create(vals)
        self._trigger_save_item_composition(record)
        return record

    def _trigger_save_item_composition(self, bom):
        _logger.info("Triggering save item composition for BOM: %s", bom)
        company = self.env.company
        if bom.product_id:
            # Fetch product template code
            product_template_code = bom.product_id.item_Cd
            pd_code = bom.product_tmpl_id.item_Cd
            # Fetch user ID
            user_id = self.env.user.id

            # Calculate total quantity from BOM lines
            total_quantity = sum(line.product_qty for line in bom.bom_line_ids)

            payload = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "itemCd": product_template_code,
                "cpstItemCd": pd_code,
                "cpstQty": total_quantity,
                "regrId": user_id,
                "regrNm": self.env.user.name,
            }
            print("Payload:", json.dumps(payload, indent=2))  # Debug payload
            _logger.debug("Payload: %s", json.dumps(payload, indent=2))  # Log payload

            url = 'http://vsdc.iswe.co.zm/sandbox/items/saveItemComposition'
            headers = {'Content-Type': 'application/json'}

            try:
                response = requests.post(url, json=payload, headers=headers)
                response.raise_for_status()
                response_data = response.json()
                message = f"API request successful. Response: {json.dumps(response_data, indent=2)}"
                print(message)
                _logger.info(message)
            except requests.exceptions.HTTPError as e:
                message = f"HTTP error occurred: {str(e)}"
                print(message)
                _logger.error(message)
            except requests.exceptions.ConnectionError as e:
                message = f"Error connecting to the server: {str(e)}"
                print(message)
                _logger.error(message)
            except requests.exceptions.Timeout as e:
                message = f"Request timed out: {str(e)}"
                print(message)
                _logger.error(message)
            except requests.exceptions.RequestException as e:
                message = f"API request failed: {str(e)}"
                print(message)
                _logger.error(message)
            except json.JSONDecodeError as e:
                message = f"Failed to parse response JSON: {str(e)}"
                print(message)
                _logger.error(message)

            # Post the message to the chatter
            if 'message' in locals():
                bom.message_post(body=message)
            else:
                bom.message_post(body="Failed to call API. Check logs for details.")
        else:
            message = "Product ID is missing, skipping API call."
            print(message)
            _logger.info(message)
            bom.message_post(body=message)
