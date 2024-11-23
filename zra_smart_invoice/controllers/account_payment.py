from odoo import http
from odoo.http import request


class AccountPaymentRegisterOverride(http.Controller):

    @http.route('/account/payment/register', type='json', auth='user')
    def payment_register(self, data, **kw):
        result = super(AccountPaymentRegisterOverride, self).payment_register(data, **kw)

        move_ids = data.get('move_ids')
        print(f"move_ids: {move_ids}")  # Debug print

        if move_ids:
            move_ids = [int(move_id) for move_id in move_ids]
            moves = request.env['account.move'].browse(move_ids)
            print(f"Moves found: {moves.ids}")  # Debug print

            for move in moves:
                move.message_post(body="Payment registered.")
                print(f"Message posted for move {move.id}")  # Debug print

        return result
