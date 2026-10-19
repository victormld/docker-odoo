from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestApprovalFlow(AccountTestInvoicingCommon):
    """Approval levels, rejection, payment and report, acting as each role."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        approver_groups = "base.group_user,payment_request.group_payment_request_approver"
        cls.requester = new_test_user(cls.env, login="flow_requester", name="Flow Requester")
        cls.area_head = new_test_user(cls.env, login="flow_area_head", name="Area Head", groups=approver_groups)
        cls.management = new_test_user(cls.env, login="flow_management", name="Management", groups=approver_groups)
        cls.treasury = new_test_user(
            cls.env, login="flow_treasury", name="Flow Treasury",
            groups="base.group_user,payment_request.group_payment_request_treasury",
        )
        cls.supplier = cls.env["res.partner"].create({"name": "Flow Supplier"})
        Level = cls.env["payment.approval.level"]
        cls.area_level = Level.create({"name": "Area", "min_amount": 0.0, "approver_id": cls.area_head.id})
        cls.management_level = Level.create({
            "name": "Management", "min_amount": 10000.0, "approver_id": cls.management.id,
        })

    def _submitted_request(self, amount=500.0, user=None, **vals):
        request = self.env["payment.request"].with_user(user or self.requester).create({
            "partner_id": self.supplier.id,
            "amount": amount,
            "concept": "Spare parts",
            **vals,
        })
        request.action_submit()
        return request

    def _approved_request(self, amount=500.0):
        request = self._submitted_request(amount)
        request.with_user(request.approver_id).action_approve()
        return request

    def _pay(self, request):
        self.env["payment.request.payment.wizard"].with_user(self.treasury).create({
            "request_id": request.id,
            "journal_id": self.company_data["default_journal_bank"].id,
        }).action_pay()

    # -- approval levels

    def test_amount_selects_approval_level(self):
        for amount, approver in ((500.0, self.area_head), (9999.99, self.area_head),
                                 (10000.0, self.management), (25000.0, self.management)):
            with self.subTest(amount=amount):
                request = self._submitted_request(amount)
                self.assertEqual(request.approver_id, approver)
                self.assertEqual(request.approval_level_id.approver_id, approver)

    def test_amount_in_other_currency_is_converted(self):
        # 0.5 units of the other currency per unit of the company currency: 6,000 are 12,000
        other_currency = self.setup_other_currency("EUR", rates=[("2016-01-01", 0.5)])
        request = self._submitted_request(6000.0, currency_id=other_currency.id)
        self.assertEqual(request.approver_id, self.management)

    def test_level_approver_request_goes_to_next_level(self):
        request = self._submitted_request(500.0, user=self.area_head)
        self.assertEqual(request.approver_id, self.management)
        # The top approver has nobody above: the request cannot be submitted
        with self.assertRaisesRegex(UserError, "no approver other than its requester"):
            self._submitted_request(25000.0, user=self.management)

    def test_submit_requires_an_applicable_level(self):
        self.area_level.min_amount = 100.0
        with self.assertRaisesRegex(UserError, "No approval level applies"):
            self._submitted_request(50.0)

    def test_submit_creates_activity_for_approver(self):
        request = self._submitted_request(500.0)
        self.assertEqual(request.activity_ids.user_id, self.area_head)
        self.assertEqual(request.activity_ids.activity_type_id, self.env.ref("mail.mail_activity_data_todo"))
        request.with_user(self.area_head).action_approve()
        self.assertFalse(request.activity_ids, "Approving closes the approver's activity")

    def test_level_validations(self):
        Level = self.env["payment.approval.level"]
        with self.assertRaises(ValidationError):
            Level.create({"name": "Negative", "min_amount": -1.0, "approver_id": self.area_head.id})
        with self.assertRaisesRegex(ValidationError, "is not an approver"):
            Level.create({"name": "Not an approver", "min_amount": 0.0, "approver_id": self.requester.id})

    # -- approval and rejection

    def test_only_assigned_approver_decides(self):
        request = self._submitted_request(500.0)
        for action in ("action_approve", "action_reject"):
            with self.subTest(action=action), self.assertRaisesRegex(AccessError, "Only Area Head"):
                getattr(request.with_user(self.management), action)()
        request.with_user(self.area_head).action_approve()
        self.assertEqual(request.state, "approved")
        self.assertTrue(request.approval_date)

    def test_reject_requires_reason_and_posts_it(self):
        request = self._submitted_request(500.0)
        Wizard = self.env["payment.request.reject.wizard"].with_user(self.area_head)
        with self.assertRaisesRegex(UserError, "Explain why"):
            Wizard.create({"request_id": request.id, "reason": "   "}).action_reject()
        self.assertEqual(request.state, "submitted")

        action = request.with_user(self.area_head).action_reject()
        self.assertEqual((action["res_model"], action["context"]["default_request_id"]),
                         ("payment.request.reject.wizard", request.id))
        reason = "The invoice was already paid"
        Wizard.create({"request_id": request.id, "reason": reason}).action_reject()
        self.assertEqual(request.state, "rejected")
        self.assertEqual(request.rejection_reason, reason)
        comment = request.message_ids.filtered(
            lambda message: reason in message.body and message.subtype_id == self.env.ref("mail.mt_comment"))
        self.assertTrue(comment, "The reason is posted in the chatter as a comment")
        self.assertIn(self.requester.partner_id, request.message_partner_ids, "The requester follows the request")
        self.assertFalse(request.activity_ids)

    # -- payment

    def test_payment_creates_posted_supplier_payment(self):
        request = self._approved_request()
        self._pay(request)
        payment = request.payment_id
        self.assertEqual(request.state, "paid")
        self.assertIn(payment.state, ("in_process", "paid"), "The payment is posted")
        self.assertEqual(
            (payment.payment_type, payment.partner_type, payment.partner_id, payment.amount, payment.currency_id),
            ("outbound", "supplier", self.supplier, 500.0, request.currency_id),
        )
        self.assertEqual(payment.memo, request.name)
        # The requester sees the payment data without accounting rights
        self.assertEqual(request.with_user(self.requester).payment_reference, payment.name)

    def test_treasury_opens_payment_wizard_and_payment(self):
        request = self._approved_request()
        action = request.with_user(self.treasury).action_open_payment_wizard()
        self.assertEqual(action["res_model"], "payment.request.payment.wizard")
        self._pay(request)
        action = request.with_user(self.treasury).action_view_payment()
        self.assertEqual((action["res_model"], action["res_id"]), ("account.payment", request.payment_id.id))

    def test_request_cannot_be_paid_twice(self):
        request = self._approved_request()
        self._pay(request)
        with self.assertRaisesRegex(UserError, "current status"):
            self._pay(request)
        self.assertEqual(self.env["account.payment"].search_count([("memo", "=", request.name)]), 1)

    def test_only_treasury_pays(self):
        request = self._approved_request()
        for user in (self.requester, self.area_head):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                request.with_user(user).action_open_payment_wizard()

    # -- report

    def test_report_shows_who_approved_and_when(self):
        request = self._approved_request()
        self._pay(request)
        # Printed by the requester: the report only uses data the requester can read
        report = self.env["ir.actions.report"].with_user(self.requester)
        html = report._render_qweb_html("payment_request.action_report_payment_request", request.ids)[0].decode()
        lang = self.env["res.lang"]._lang_get(self.requester.lang)
        approval_day = fields.Datetime.context_timestamp(report, request.approval_date).strftime(lang.date_format)
        for expected in (request.name, "Area Head", approval_day, request.payment_reference):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)
