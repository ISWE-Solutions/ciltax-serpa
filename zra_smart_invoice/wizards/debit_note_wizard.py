from odoo import models, fields, api

class DebitNoteWizard(models.TransientModel):
    _name = 'debit.note.wizard'
    _description = 'Wizard to create Debit Note'

    reason = fields.Selection([
        ('01', 'Wrong quantity invoiced'),
        ('02', 'Wrong invoice amount'),
        ('03', 'Omitted item'),
        ('04', 'Other [specify]'),
    ], string='Reason', required=True)

    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    move_id = fields.Many2one('account.move', string='Move', required=True)

    def default_get(self, fields):
        res = super(DebitNoteWizard, self).default_get(fields)
        res['move_id'] = self._context.get('default_move_id')
        return res

    def create_debit_note(self):
        self.ensure_one()
        move = self.move_id

        # Call the methods from the account.move model
        reason = self.reason
        # move.create_debit_note_api_call()
        move._process_moves_debit()


        return {'type': 'ir.actions.act_window_close'}
