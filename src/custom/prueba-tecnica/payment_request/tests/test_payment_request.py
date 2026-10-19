from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestPaymentRequest(AccountTestInvoicingCommon):
    """Every test acts as a real user of each group: none runs as superuser."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.requester = new_test_user(cls.env, login="pr_requester", name="Requester")
        cls.other_requester = new_test_user(cls.env, login="pr_other_requester", name="Other Requester")
        cls.approver = new_test_user(
            cls.env, login="pr_approver", name="Approver",
            groups="base.group_user,payment_request.group_payment_request_approver",
        )
        cls.treasury = new_test_user(
            cls.env, login="pr_treasury", name="Treasury",
            groups="base.group_user,payment_request.group_payment_request_treasury",
        )
        cls.manager = new_test_user(
            cls.env, login="pr_manager", name="Manager",
            groups="base.group_user,payment_request.group_payment_request_approver",
        )
        cls.supplier = cls.env["res.partner"].create({"name": "Test Supplier"})
        cls.area_level = cls.env["payment.approval.level"].create({
            "name": "Area", "min_amount": 0.0, "approver_id": cls.approver.id,
        })
        cls.management_level = cls.env["payment.approval.level"].create({
            "name": "Management", "min_amount": 10000.0, "approver_id": cls.manager.id,
        })

    def _new_request(self, user=None, **vals):
        return self.env["payment.request"].with_user(user or self.requester).create({
            "partner_id": self.supplier.id,
            "amount": 100.0,
            "concept": "Office supplies",
            **vals,
        })

    def _pay(self, request, user=None):
        self.env["payment.request.payment.wizard"].with_user(user or self.treasury).create({
            "request_id": request.id,
            "journal_id": self.company_data["default_journal_bank"].id,
        }).action_pay()

    def _form_arch(self, user):
        return self.env["payment.request"].with_user(user).get_views([(False, "form")])["views"]["form"]["arch"]

    def test_full_flow(self):
        request = self._new_request()
        self.assertEqual(request.state, "draft")
        self.assertTrue(request.name.startswith(f"SP/{fields.Date.today().year}/"))
        request.action_submit()
        self.assertEqual(request.state, "submitted")
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")
        self._pay(request)
        self.assertEqual(request.state, "in_process", "Registered by treasury, not yet confirmed by accounting")

    def test_requester_sees_only_own_requests(self):
        own = self._new_request()
        other = self._new_request(self.other_requester)
        visible = self.env["payment.request"].with_user(self.requester).search([])
        self.assertIn(own, visible)
        self.assertNotIn(other, visible)
        self.assertLessEqual(own | other, self.env["payment.request"].with_user(self.approver).search([]))

    def test_requester_cannot_request_for_someone_else(self):
        with self.assertRaises(AccessError):
            self._new_request(requester_id=self.other_requester.id)

    def test_requester_cannot_approve(self):
        request = self._new_request()
        request.action_submit()
        for user in (self.requester, self.treasury):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                request.with_user(user).action_approve()
        self.assertEqual(request.state, "submitted")

    def test_approver_cannot_approve_own_request(self):
        # The area approver's own request goes to the next level up
        request = self._new_request(self.approver)
        request.action_submit()
        self.assertEqual(request.approver_id, self.manager)
        with self.assertRaises(AccessError):
            request.action_approve()

    def test_buttons_only_for_their_group(self):
        # Odoo removes from the view the nodes restricted to groups the user does not have
        self.assertNotIn('name="action_approve"', self._form_arch(self.requester))
        self.assertNotIn('name="action_open_payment_wizard"', self._form_arch(self.requester))
        self.assertIn('name="action_approve"', self._form_arch(self.approver))
        self.assertNotIn('name="action_open_payment_wizard"', self._form_arch(self.approver))
        self.assertIn('name="action_open_payment_wizard"', self._form_arch(self.treasury))
        self.assertNotIn('name="action_approve"', self._form_arch(self.treasury))

    def test_submitted_request_cannot_be_modified(self):
        request = self._new_request()
        request.action_submit()
        other_supplier = self.env["res.partner"].create({"name": "Other Supplier"})
        for vals in ({"amount": 999.0}, {"partner_id": other_supplier.id}, {"concept": "Changed"}):
            with self.subTest(vals=vals), self.assertRaisesRegex(UserError, "cannot be modified"):
                request.write(vals)
        with self.assertRaisesRegex(UserError, "cannot be modified"):
            request.with_user(self.approver).write({"amount": 1.0})
        self.assertEqual(request.amount, 100.0)

    def test_amount_must_be_positive(self):
        for amount in (0.0, -50.0):
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                self._new_request(amount=amount)

    def test_actions_only_in_their_status(self):
        request = self._new_request()
        with self.assertRaisesRegex(UserError, "current status"):
            request.with_user(self.approver).action_approve()
        with self.assertRaisesRegex(UserError, "current status"):
            request.with_user(self.treasury).action_open_payment_wizard()
        request.action_submit()
        with self.assertRaisesRegex(UserError, "current status"):
            request.action_submit()

    def test_only_treasury_pays(self):
        request = self._new_request()
        request.action_submit()
        request.with_user(self.approver).action_approve()
        for user in (self.requester, self.approver):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                request.with_user(user).action_open_payment_wizard()
        self.assertEqual(request.state, "approved")

    def test_only_drafts_can_be_deleted(self):
        draft = self._new_request()
        draft.unlink()
        self.assertFalse(draft.exists())
        submitted = self._new_request()
        submitted.action_submit()
        with self.assertRaisesRegex(UserError, "Only draft"):
            submitted.unlink()

    def test_only_approvers_reject(self):
        request = self._new_request()
        request.action_submit()
        for user in (self.requester, self.treasury):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                request.with_user(user).action_reject()
        self.env["payment.request.reject.wizard"].with_user(self.approver).create({
            "request_id": request.id,
            "reason": "Duplicated invoice",
        }).action_reject()
        self.assertEqual(request.state, "rejected")
