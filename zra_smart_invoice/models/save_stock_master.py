import requests
from odoo import models, api
import logging
import json

_logger = logging.getLogger(__name__)


class StockChangeProductQty(models.TransientModel):
    _inherit = 'stock.change.product.qty'

    def change_product_qty(self):
        config_settings = self.env['res.company'].sudo().browse(self.env.company.id)
        current_user = self.env.user
        _logger.info('Entering change_product_qty method.')
        print('Entering change_product_qty method.')

        res = super(StockChangeProductQty, self).change_product_qty()

        for record in self:
            product = record.product_id
            new_qty = record.new_quantity
            product_template = product.product_tmpl_id

            _logger.info(f'Changing quantity for product: {product.display_name} to {new_qty}')
            print(f'Changing quantity for product: {product.display_name} to {new_qty}')

            # Prepare the payload for the POST request
            company = self.env.company
            payload = {
                "tpin": company.tpin,
                "bhfId": company.bhf_id,
                "regrId": current_user.id,
                "regrNm": current_user.name,
                "modrNm": current_user.name,
                "modrId": current_user.id,
                "stockItemList": [
                    {
                        "itemCd": product_template.item_Cd,
                        "rsdQty": new_qty
                    }
                ]
            }

            try:
                print('Payload being sent:', json.dumps(payload, indent=4))
                # Make the POST request to the given endpoint
                response = requests.post(config_settings.stock_master_endpoint, json=payload)
                response.raise_for_status()
                result_msg = response.json().get('resultMsg', 'No result message received')
                _logger.info(f'Endpoint response: {result_msg}')
                print(f'Endpoint response: {result_msg}')
            except requests.exceptions.RequestException as e:
                result_msg = str(e)
                _logger.error(f'Error during POST request: {result_msg}')
                print(f'Error during POST request: {result_msg}')

            # Post the resultMsg to the chatter
            product_template.message_post(
                body='Quantity of product {} has been updated to {}. Endpoint response: {}'.format(product.display_name,
                                                                                                   new_qty, result_msg),
                subtype_id=self.env.ref('mail.mt_note').id
            )

            _logger.info(f'Message posted for product: {product.display_name} on product.template')
            print(f'Message posted for product: {product.display_name} on product.template')

        _logger.info('Exiting change_product_qty method.')
        print('Exiting change_product_qty method.')

        return res