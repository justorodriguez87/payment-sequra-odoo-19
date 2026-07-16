# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models
from odoo.http import request

from odoo.addons.payment import utils as payment_utils


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    @api.model
    def _get_compatible_providers(self, *args, sale_order_id=None, report=None, **kwargs):
        """Override of `payment` to exclude seQura when the cart contains products
        flagged as not financeable (e.g. gift cards), as required by seQura."""
        providers = super()._get_compatible_providers(
            *args, sale_order_id=sale_order_id, report=report, **kwargs
        )
        sequra_providers = providers.filtered(lambda p: p.code == 'sequra')
        if not sequra_providers:
            return providers

        order = None
        if sale_order_id:
            order = self.env['sale.order'].sudo().browse(sale_order_id).exists()
        else:  # Fall back on the current website cart, if any.
            try:
                if request and getattr(request, 'website', None):
                    order = request.website.sale_get_order()
            except Exception:  # noqa: BLE001 - never break the payment page.
                order = None

        if order and any(
            line.product_id.product_tmpl_id.sequra_excluded
            for line in order.order_line if not line.display_type
        ):
            providers -= sequra_providers
            payment_utils.add_to_report(
                report,
                sequra_providers,
                available=False,
                reason=_("the cart contains products not financeable with seQura"),
            )
        return providers

    @api.model
    def _sequra_get_widget_config(self, website):
        """Return the configuration of the seQura promotional widget for a website.

        :param website website: The website on which the widget is rendered.
        :return: The widget configuration, or None if no eligible provider is found.
        :rtype: dict|None
        """
        provider = self.sudo().search([
            ('code', '=', 'sequra'),
            ('state', 'in', ['enabled', 'test']),
            ('is_published', '=', True),
            ('website_id', 'in', (False, website.id)),
            *self.env['payment.provider']._check_company_domain(website.company_id.id),
        ], limit=1)
        if not provider or not provider.sequra_assets_key:
            return None

        env_name = 'live' if provider.state == 'enabled' else 'sandbox'
        merchant = provider.sequra_merchant_ref
        asset_key = provider.sequra_assets_key
        product = provider.sequra_product_code or 'pp3'
        return {
            'merchant': merchant,
            'assetKey': asset_key,
            'products': [product],
            'product': product,
            'scriptUri': f'https://{env_name}.sequracdn.com/assets/sequra-checkout.min.js',
            'decimalSeparator': ',',
            'thousandSeparator': '.',
            'locale': (self.env.lang or 'es_ES').replace('_', '-'),
            'currency': 'EUR',
        }
