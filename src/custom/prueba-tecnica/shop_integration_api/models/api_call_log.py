from odoo import api, fields, models


class ShopApiCallLog(models.Model):
    """One row per API call, successful or not.

    It deliberately does NOT store headers, body or query string, so the API key
    can never end up in this table.
    """
    _name = 'shop.api.call.log'
    _description = 'Shop API Call Log'
    _order = 'id desc'

    endpoint = fields.Char(string='Endpoint', required=True, readonly=True)
    method = fields.Char(string='HTTP Method', required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True, ondelete='set null')
    status_code = fields.Integer(string='Response Code', readonly=True)
    duration_ms = fields.Integer(string='Duration (ms)', readonly=True)
    error_code = fields.Char(string='Error Code', readonly=True)

    @api.depends('method', 'endpoint', 'status_code')
    def _compute_display_name(self):
        for log in self:
            log.display_name = f'{log.method} {log.endpoint} ({log.status_code})'
