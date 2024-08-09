# -*- coding: utf-8 -*-

from odoo import models, fields, api ,_
from odoo.exceptions import UserError


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    standard_workflow = fields.Boolean()
    state = fields.Selection(selection_add=[
        ('waiting_approval_1', 'Waiting approved'),
        ('waiting_approval_2', 'Waiting approved'), ('approved',)
    ])

    @api.depends('sheet_id', 'sheet_id.account_move_id', 'sheet_id.state', 'sheet_id.standard_workflow')
    def _compute_state(self):
        for expense in self:
            if not expense.sheet_id or expense.sheet_id.state == 'draft':
                expense.state = "draft"
            elif expense.sheet_id.state == "waiting_approval_1" and not expense.sheet_id.standard_workflow:
                expense.state = "waiting_approval_1"
            elif expense.sheet_id.state == "waiting_approval_2" and not expense.sheet_id.standard_workflow:
                expense.state = "waiting_approval_2"
            elif expense.sheet_id.state == "cancel":
                expense.state = "refused"
            elif expense.sheet_id.state == "approve" or expense.sheet_id.state == "post":
                expense.state = "approved"
            elif not expense.sheet_id.account_move_id:
                expense.state = "reported"
            else:
                expense.state = "done"


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    standard_workflow = fields.Boolean(string="Custom workflow", default=True)
    first_confirmation = fields.Boolean()
    second_confirmation = fields.Boolean()
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submit', 'Submitted'),
        ('waiting_approval_1', 'Waiting approved'),
        ('waiting_approval_2', 'Waiting approved'),
        ('approve', 'Approved'),
        ('post', 'Posted'),
        ('done', 'Done'),
        ('cancel', 'Refused')
    ], string='Status', index=True, readonly=True, tracking=True, copy=False, default='draft', required=True, help='Expense Report State')

    def action_first_validation(self):
        for sheet in self:
            if sheet.second_confirmation:
                sheet.approve_expense_sheets()
            else:
                sheet.state = 'waiting_approval_1'
                sheet.first_confirmation = True

    def action_second_validation(self):
        for expense in self:
            if expense.first_confirmation:
                expense.approve_expense_sheets()
            else:
                expense.state = 'waiting_approval_2'
                expense.second_confirmation = True

    def _do_approve(self):
        self._check_can_approve()

        notification = {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('There are no expense reports to approve.'),
                'type': 'warning',
                'sticky': False,  #True/False will display for few seconds if false
            },
        }
        if self.standard_workflow:
            filtered_sheet = self.filtered(lambda s: s.state in ['submit', 'draft'])
        else:
            filtered_sheet = self.filtered(lambda s: s.state in ['waiting_approval_1', 'waiting_approval_2', 'draft'])

        if not filtered_sheet:
            return notification
        for sheet in filtered_sheet:
            sheet.write({
                'state': 'approve',
                'user_id': sheet.user_id.id or self.env.user.id,
                'approval_date': fields.Date.context_today(sheet),
            })
        notification['params'].update({
            'title': _('The expense reports were successfully approved.'),
            'type': 'success',
            'next': {'type': 'ir.actions.act_window_close'},
        })

        self.activity_update()
        return notification

    def activity_update(self):
        for expense_report in self.filtered(lambda hol: hol.state in ['waiting_approval_2', 'waiting_approval_1']):
            self.activity_schedule(
                'hr_expense.mail_act_expense_approval',
                user_id=expense_report.sudo()._get_responsible_for_approval().id or self.env.user.id)
        self.filtered(lambda hol: hol.state == 'approve').activity_feedback(['hr_expense.mail_act_expense_approval'])
        self.filtered(lambda hol: hol.state in ('draft', 'cancel')).activity_unlink(['hr_expense.mail_act_expense_approval'])
