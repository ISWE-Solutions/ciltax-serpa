from odoo import http
from odoo.http import request
import json
import logging
from odoo.exceptions import ValidationError, UserError


class CSRFTokenController(http.Controller):

    @http.route('/api/get_csrf_token', type='json', auth='public', methods=['GET'])
    def get_csrf_token(self, **kwargs):
        csrf_token = request.csrf_token()
        return request.make_response(csrf_token, headers={
            'Content-Type': 'text/plain',
            'Access-Control-Allow-Origin': '*'
        })


class CustomPOSController(http.Controller):

    @http.route('/api/data', type='http', auth='user', methods=['POST', 'OPTIONS'])
    def api_data(self, **kwargs):
        print(f"INSIDE FUNCTION")
        if request.httprequest.method == 'OPTIONS':
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            }
            return request.make_response('', headers=headers)

        try:
            token = request.httprequest.headers.get('X-CSRF-Token')
            print(f"CSRF Token: {token}")  # Log the CSRF token for debugging
            order_data = json.loads(request.httprequest.data.decode('utf-8'))
            sales_payload = order_data.get('sales_payload')
            stock_payload = order_data.get('stock_payload')

            api_response = self._process_api_data(sales_payload, stock_payload)

            headers = {
                'Access-Control-Allow-Origin': '*'
            }
            return request.make_response(json.dumps(api_response), headers=headers)

        except Exception as e:
            headers = {
                'Access-Control-Allow-Origin': '*'
            }
            return request.make_response(json.dumps({
                'error': str(e)
            }), headers=headers)

    def _process_api_data(self, sales_payload, stock_payload):
        SalesModel = request.env['account.move'].sudo()
        result = SalesModel.create_invoice({
            'sales_payload': sales_payload,
            'stock_payload': stock_payload
        })
        return result
