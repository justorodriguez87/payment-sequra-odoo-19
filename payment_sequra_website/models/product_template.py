# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    sequra_excluded = fields.Boolean(
        string="No financiable con seQura",
        help="Si está marcado, seQura no se ofrecerá como método de pago cuando este "
             "producto esté en el carrito, y no se mostrarán widgets promocionales de "
             "seQura en su ficha. Requerido por seQura para tarjetas regalo y otros "
             "productos no financiables.",
        default=False,
    )
