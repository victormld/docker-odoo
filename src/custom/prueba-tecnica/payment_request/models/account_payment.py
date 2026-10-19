from odoo import _, fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    payment_request_id = fields.Many2one(
        "payment.request", string="Payment Request", readonly=True, copy=False, index="btree_not_null")

    def write(self, vals):
        res = super().write(vals)
        if vals.get("state") in ("canceled", "rejected"):
            status = dict(self._fields["state"]._description_selection(self.env))[vals["state"]]
            for payment in self:
                payment._release_payment_request(
                    _("Payment %(payment)s is now “%(status)s” in accounting.", payment=payment.name, status=status))
        return res

    def unlink(self):
        for payment in self:
            payment._release_payment_request(_("Payment %s was deleted in accounting.", payment.name))
        return super().unlink()

    def _release_payment_request(self, reason):
        # sudo: whoever cancels the payment in accounting may not have access to the request
        request = self.payment_request_id.sudo()
        # Only the payment currently linked counts: an older, replaced payment no longer pays the request
        if request and request.payment_id == self:
            request._release_payment(reason)

    def action_view_payment_request(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "payment.request",
            "res_id": self.payment_request_id.id,
            "view_mode": "form",
        }
