import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Align the requests paid before 18.0.1.1.0 with the status of their payment.

    Until then a request was paid as soon as treasury registered the payment. Now its status
    follows the payment, but turning an existing field into a computed one does not
    recompute the stored values: this does it once. Running it again changes nothing.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # The chatter keeps the status labels in the language of the change: use the company's
    admin = env.ref("base.user_admin", raise_if_not_found=False)
    if admin and admin.lang:
        env = env(context={"lang": admin.lang})
    requests = env["payment.request"].search([("payment_id", "!=", False)])
    env.add_to_compute(requests._fields["state"], requests)
    env.flush_all()
    counts = {state: len(requests.filtered(lambda request, s=state: request.state == s))
              for state in ("in_process", "paid")}
    _logger.info("%s payment requests now follow the status of their payment: %s", len(requests), counts)
