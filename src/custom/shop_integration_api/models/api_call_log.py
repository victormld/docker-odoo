from odoo import api, fields, models


class ShopApiCallLog(models.Model):
    """Una fila por llamada a la API (exitosa o fallida).

    Deliberadamente NO guarda cabeceras, cuerpo ni query string: así la API key
    nunca puede terminar en esta tabla.
    """
    _name = 'shop.api.call.log'
    _description = 'Registro de llamadas a la API de la tienda'
    _order = 'id desc'

    endpoint = fields.Char(string='Endpoint', required=True, readonly=True)
    method = fields.Char(string='Método HTTP', required=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Usuario', readonly=True, ondelete='set null')
    status_code = fields.Integer(string='Código de respuesta', readonly=True)
    duration_ms = fields.Integer(string='Duración (ms)', readonly=True)
    error_code = fields.Char(string='Código de error', readonly=True)

    @api.depends('method', 'endpoint', 'status_code')
    def _compute_display_name(self):
        for log in self:
            log.display_name = f'{log.method} {log.endpoint} ({log.status_code})'
