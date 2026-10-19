import re

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestSpanishTranslation(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_VE")
        # account too: the payment status shown in the request's notes comes from it
        cls.env["ir.module.module"]._load_module_terms(["account", "payment_request"], ["es_VE"], overwrite=True)
        cls.requester = new_test_user(cls.env, login="es_requester", name="Requester", lang="en_US")
        cls.approver = new_test_user(
            cls.env, login="es_approver", name="Aprobador", lang="es_VE",
            groups="base.group_user,payment_request.group_payment_request_approver",
        )
        cls.treasury = new_test_user(
            cls.env, login="es_treasury", name="Tesorería", lang="es_VE",
            groups="base.group_user,payment_request.group_payment_request_treasury",
        )
        cls.env["payment.approval.level"].create({"name": "Área", "min_amount": 0.0, "approver_id": cls.approver.id})
        cls.supplier = cls.env["res.partner"].create({"name": "Proveedor"})

    def _request(self):
        return self.env["payment.request"].with_user(self.requester).with_context(lang="en_US").create({
            "partner_id": self.supplier.id,
            "amount": 500.0,
            "concept": "Repuestos",
        })

    def test_labels_and_data_in_spanish(self):
        env = self.env(context=dict(self.env.context, lang="es_VE"))
        field_info = env["payment.request"].fields_get(["approver_id", "state", "payment_state"], ["string", "selection"])
        self.assertEqual(field_info["approver_id"]["string"], "Aprobador")
        self.assertEqual(dict(field_info["state"]["selection"])["submitted"], "Enviada")
        self.assertEqual(field_info["payment_state"]["string"], "Estado del pago")
        self.assertEqual(env.ref("payment_request.group_payment_request_treasury").name, "Tesorería")
        self.assertEqual(env.ref("payment_request.action_report_payment_request").print_report_name,
                         "'Solicitud de pago - %s' % object.name")
        # Not in Odoo's export: added by hand to the template and to es.po
        self.assertEqual(env.ref("base.module_payment_request").shortdesc, "Solicitudes de pago")

    def test_messages_in_spanish_keep_their_variable(self):
        request = self._request().with_context(lang="es_VE")
        with self.assertRaisesRegex(ValidationError, r"^El monto debe ser mayor que cero\.$"):
            request.write({"amount": 0.0})
        expected = f"Esta acción no está disponible para {request.name} en su estado actual."
        with self.assertRaisesRegex(UserError, f"^{re.escape(expected)}$"):
            request.with_user(self.approver).action_approve()

    def test_approval_activity_in_approver_language(self):
        # The requester works in English; the approver reads the activity in Spanish
        request = self._request()
        request.action_submit()
        self.assertEqual(request.activity_ids.summary, f"Aprobar o rechazar la solicitud de pago {request.name}")

    def test_rejected_payment_note_in_spanish(self):
        request = self._request()
        request.action_submit()
        request.with_user(self.approver).action_approve()
        self.env["payment.request.payment.wizard"].with_user(self.treasury).create({
            "request_id": request.id,
            "journal_id": self.company_data["default_journal_bank"].id,
        }).action_pay()
        payment = request.payment_id.with_user(self.treasury).with_context(lang="es_VE")
        payment_name = payment.name
        payment.action_reject()
        expected = (f"El pago {payment_name} ahora está “Rechazado” en contabilidad. "
                    "La solicitud vuelve a estar aprobada para que tesorería la pague de nuevo.")
        self.assertTrue(request.message_ids.filtered(lambda message: expected in str(message.body)))
