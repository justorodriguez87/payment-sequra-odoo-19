# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

from odoo import _, api, models, fields, release
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools.urls import urljoin

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_sequra import const
from odoo.addons.payment_sequra.controllers.main import SequraController


_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    sequra_order_url = fields.Char(
        string="seQura Order URL",
        help="La URL del pedido en seQura (header Location de la solicitud), usada "
             "para recuperar el formulario de identificación y confirmar el pedido.",
        readonly=True,
        copy=False,
    )

    # === PAYMENT FLOW: RENDERING === #

    def _get_specific_rendering_values(self, processing_values):
        """Override of `payment` to return seQura-specific rendering values.

        The redirect form does not post to seQura directly: it posts to a local
        controller that starts the order solicitation against the seQura API and
        renders the identification form returned by seQura.

        Note: self.ensure_one() from `_get_processing_values`.

        :param dict processing_values: The generic processing values of the transaction.
        :return: The dict of provider-specific rendering values.
        :rtype: dict
        """
        if self.provider_code != 'sequra':
            return super()._get_specific_rendering_values(processing_values)

        base_url = self.provider_id.get_base_url()
        return {
            'api_url': urljoin(base_url, SequraController._checkout_url),
            'reference': self.reference,
            'access_token': payment_utils.generate_access_token(self.reference),
        }

    # === PAYMENT FLOW: SEQURA API === #

    def _sequra_start_checkout(self):
        """Start the seQura order solicitation and fetch the identification form.

        Flow:
        1. POST /orders with the order payload (state '') -> 204 + `Location` header.
        2. GET {location}/form_v2 (Accept: text/html) -> HTML/JS identification form.

        Note: self.ensure_one()

        :return: The HTML of the seQura identification form, to embed in the checkout
                 page.
        :rtype: str
        :raise ValidationError: If seQura rejects the solicitation.
        """
        self.ensure_one()

        # 1. Start the solicitation.
        payload = self._sequra_prepare_order_payload(state='')
        response = self.provider_id._sequra_make_request(
            '/orders', method='POST', json_payload=payload, reference=self.reference
        )
        if response.status_code != 204:
            error_msg = self._sequra_extract_errors(response)
            _logger.warning(
                "seQura solicitation refused for transaction %s: %s (HTTP %s)",
                self.reference, error_msg, response.status_code,
            )
            raise ValidationError(_(
                "seQura: The payment request was refused by seQura. %s", error_msg
            ))
        order_url = response.headers.get('Location')
        if not order_url:
            raise ValidationError(
                _("seQura: The provider did not return the order location.")
            )
        self.sequra_order_url = order_url
        self._set_pending()

        # 2. Fetch the identification form.
        endpoint = f'{order_url}/form_v2'
        if self.provider_id.sequra_product_code:
            endpoint += f'?product={self.provider_id.sequra_product_code}'
        response = self.provider_id._sequra_make_request(
            endpoint, method='GET', headers={'Accept': 'text/html'},
            reference=self.reference,
        )
        if response.status_code != 200:
            raise ValidationError(
                _("seQura: Unable to retrieve the seQura payment form.")
            )
        return response.text

    def _sequra_confirm_order(self):
        """Confirm the order on seQura after an approved IPN.

        seQura requires a PUT on the order URL with the same payload and the order
        state set to 'confirmed'. seQura re-validates the cart totals server-side and
        answers 200 on success or 409 if the cart changed since the solicitation.

        Note: self.ensure_one()

        :return: The raw response of the confirmation request.
        :rtype: requests.Response
        """
        self.ensure_one()
        payload = self._sequra_prepare_order_payload(state='confirmed')
        return self.provider_id._sequra_make_request(
            self.sequra_order_url, method='PUT', json_payload=payload,
            reference=self.reference,
        )

    @api.model
    def _sequra_extract_errors(self, response):
        """Extract a readable error message from a seQura API response.

        :param requests.Response response: The response of a seQura API request.
        :return: The error message, if any.
        :rtype: str
        """
        try:
            errors = response.json().get('errors', [])
            return '; '.join(str(e) for e in errors)
        except ValueError:
            return response.text[:500] if response.text else response.reason or ''

    # === PAYLOAD BUILDERS === #

    def _sequra_prepare_order_payload(self, state=''):
        """Build the seQura order payload for the solicitation or confirmation.

        See https://docs.sequrapi.com/ for the payload structure.

        :param str state: The seQura order state: '' (solicitation) or 'confirmed'.
        :return: The order payload.
        :rtype: dict
        """
        self.ensure_one()

        base_url = self.provider_id.get_base_url()
        signature = payment_utils.generate_access_token(self.reference)
        return_url = urljoin(base_url, SequraController._return_url)
        # seQura replaces the literal 'SQ_PRODUCT_CODE' with the chosen product code.
        return_url += f'?reference={self.reference}&product=SQ_PRODUCT_CODE'

        merchant_values = {
            'id': self.provider_id.sequra_merchant_ref,
            'notify_url': urljoin(base_url, SequraController._webhook_url),
            'notification_parameters': {
                'reference': self.reference,
                'signature': signature,
            },
            'return_url': return_url,
            'abort_url': urljoin(base_url, '/payment/status'),
        }

        sale_order = self._sequra_get_sale_order()
        merchant_reference = {'order_ref_1': self.reference}
        if sale_order:
            merchant_reference['order_ref_2'] = sale_order.name

        delivery_address, invoice_address = self._sequra_prepare_addresses(sale_order)

        payload = {
            'order': {
                'state': state,
                'merchant': merchant_values,
                'merchant_reference': merchant_reference,
                'cart': {
                    'cart_ref': self.reference,
                    'currency': self.currency_id.name or 'EUR',
                    'gift': False,
                    'items': self._sequra_prepare_cart_items(sale_order),
                    'order_total_with_tax': payment_utils.to_minor_currency_units(
                        self.amount, self.currency_id
                    ),
                },
                'delivery_method': self._sequra_prepare_delivery_method(sale_order),
                'delivery_address': delivery_address,
                'invoice_address': invoice_address,
                'customer': self._sequra_prepare_customer(),
                'gui': {
                    'layout': 'desktop',
                },
                'platform': {
                    'name': 'Odoo',
                    'version': release.version,
                    'plugin_version': '19.0.1.0.0',
                    'uname': '',
                    'db_name': 'postgresql',
                    'db_version': '',
                },
            },
        }
        return payload

    def _sequra_get_sale_order(self):
        """Return the sale order linked to the transaction, if any.

        :return: The linked sale order or an empty/None value.
        """
        # `sale_order_ids` only exists if the `sale` module is installed.
        if 'sale_order_ids' in self._fields and self.sale_order_ids:
            return self.sale_order_ids[:1]
        return None

    def _sequra_prepare_cart_items(self, sale_order=None):
        """Build the seQura cart items.

        seQura validates that the sum of the items' `total_with_tax` matches the
        order's `order_total_with_tax`; a final adjustment item covers any rounding
        difference or partial payments (e.g. down payments).

        :param sale.order sale_order: The sale order linked to the transaction, if any.
        :return: The list of cart items.
        :rtype: list
        """
        currency = self.currency_id
        order_total = payment_utils.to_minor_currency_units(self.amount, currency)
        items = []

        if sale_order:
            for line in sale_order.order_line:
                if line.display_type:  # Section titles and notes.
                    continue
                total_with_tax = payment_utils.to_minor_currency_units(
                    line.price_total, currency
                )
                if getattr(line, 'is_delivery', False):
                    items.append({
                        'type': 'handling',
                        'reference': 'shipping',
                        'name': line.name or 'Envío',
                        'tax_rate': 0,
                        'total_with_tax': total_with_tax,
                    })
                elif total_with_tax < 0:  # Discounts, coupons, refund-like lines.
                    items.append({
                        'type': 'discount',
                        'reference': str(line.product_id.id or line.id),
                        'name': line.name or 'Descuento',
                        'total_with_tax': total_with_tax,
                    })
                else:
                    quantity = int(line.product_uom_qty) or 1
                    items.append({
                        'reference': line.product_id.default_code
                                     or str(line.product_id.id or line.id),
                        'name': line.name or line.product_id.display_name,
                        'quantity': quantity,
                        'price_with_tax': round(total_with_tax / quantity),
                        'total_with_tax': total_with_tax,
                        'downloadable': False,
                    })

        if not items:  # Portal payment of an invoice, payment link, etc.
            items.append({
                'reference': self.reference,
                'name': _("Payment %s", self.reference),
                'quantity': 1,
                'price_with_tax': order_total,
                'total_with_tax': order_total,
                'downloadable': False,
            })

        # Rounding / partial payment adjustment so that items always sum to the total
        # (seQura rejects orders whose items don't add up to `order_total_with_tax`).
        items_total = sum(i['total_with_tax'] for i in items)
        difference = order_total - items_total
        if difference:
            item_type = 'discount' if difference < 0 else 'handling'
            adjustment = {
                'type': item_type,
                'reference': 'adjustment',
                'name': 'Ajuste',
                'total_with_tax': difference,
            }
            if item_type == 'handling':
                adjustment['tax_rate'] = 0
            items.append(adjustment)

        return items

    def _sequra_prepare_delivery_method(self, sale_order=None):
        """Build the seQura delivery method values.

        :param sale.order sale_order: The sale order linked to the transaction, if any.
        :return: The delivery method values.
        :rtype: dict
        """
        if sale_order and 'carrier_id' in sale_order._fields and sale_order.carrier_id:
            return {'name': sale_order.carrier_id.name}
        return {'name': 'default'}

    def _sequra_prepare_addresses(self, sale_order=None):
        """Build the seQura delivery and invoice addresses.

        :param sale.order sale_order: The sale order linked to the transaction, if any.
        :return: The delivery and invoice addresses.
        :rtype: tuple(dict, dict)
        """
        if sale_order:
            delivery = self._sequra_format_partner_address(
                sale_order.partner_shipping_id or sale_order.partner_id
            )
            invoice = self._sequra_format_partner_address(
                sale_order.partner_invoice_id or sale_order.partner_id
            )
        else:
            delivery = invoice = self._sequra_format_tx_address()
        return delivery, invoice

    def _sequra_format_partner_address(self, partner):
        """Format a res.partner record as a seQura address.

        :param res.partner partner: The partner to format.
        :return: The seQura address values.
        :rtype: dict
        """
        first_name, last_name = payment_utils.split_partner_name(partner.name or '')
        address = {
            'given_names': first_name or (partner.name or ''),
            'surnames': last_name or '',
            'company': partner.commercial_company_name or '',
            'address_line_1': partner.street or '',
            'address_line_2': partner.street2 or '',
            'postal_code': partner.zip or '',
            'city': partner.city or '',
            'country_code': partner.country_id.code or 'ES',
            'phone': partner.phone or '',
            'mobile_phone': partner.phone or '',
            'state': partner.state_id.name or '',
        }
        if partner.vat:
            address['vat_number'] = partner.vat
        return address

    def _sequra_format_tx_address(self):
        """Format the transaction's partner fields as a seQura address.

        Used when no sale order is linked (invoice payments, payment links).

        :return: The seQura address values.
        :rtype: dict
        """
        first_name, last_name = payment_utils.split_partner_name(self.partner_name or '')
        return {
            'given_names': first_name or (self.partner_name or ''),
            'surnames': last_name or '',
            'company': '',
            'address_line_1': self.partner_address or '',
            'address_line_2': '',
            'postal_code': self.partner_zip or '',
            'city': self.partner_city or '',
            'country_code': self.partner_country_id.code or 'ES',
            'phone': self.partner_phone or '',
            'mobile_phone': self.partner_phone or '',
            'state': self.partner_state_id.name or '',
        }

    def _sequra_prepare_customer(self):
        """Build the seQura customer values.

        :return: The customer values.
        :rtype: dict
        """
        first_name, last_name = payment_utils.split_partner_name(self.partner_name or '')
        lang = (self.partner_id.lang or 'es_ES').replace('_', '-')
        customer = {
            'given_names': first_name or (self.partner_name or ''),
            'surnames': last_name or '',
            'email': self.partner_email or '',
            'ref': self.partner_id.id,
            'language_code': lang,
            'logged_in': 'unknown',
        }
        if self.partner_id.vat:
            customer['nin'] = self.partner_id.vat

        # Enrich with request data when building from an HTTP context.
        try:
            if request:
                environ = request.httprequest.environ
                forwarded = environ.get('HTTP_X_FORWARDED_FOR')
                customer['ip_number'] = (
                    forwarded.split(',')[0].strip() if forwarded
                    else environ.get('REMOTE_ADDR', '')
                )
                customer['user_agent'] = environ.get('HTTP_USER_AGENT', '')
        except Exception:  # noqa: BLE001 - never block a payment on metadata.
            pass
        return customer

    # === PAYMENT FLOW: PROCESSING === #

    @api.model
    def _extract_reference(self, provider_code, payment_data):
        """Override of `payment` to extract the reference from the payment data."""
        if provider_code != 'sequra':
            return super()._extract_reference(provider_code, payment_data)
        return payment_data.get('reference') or payment_data.get('order_ref_1')

    def _extract_amount_data(self, payment_data):
        """Override of `payment` to skip the amount validation.

        seQura's IPN does not include the amount; seQura itself validates the cart
        totals server-side when the order is confirmed with the PUT request.
        """
        if self.provider_code != 'sequra':
            return super()._extract_amount_data(payment_data)
        return None

    def _apply_updates(self, payment_data):
        """Override of `payment` to update the transaction based on the payment data."""
        if self.provider_code != 'sequra':
            return super()._apply_updates(payment_data)

        if payment_data.get('order_ref'):
            self.provider_reference = payment_data['order_ref']

        status = (payment_data.get('sq_state') or payment_data.get('event') or '').lower()
        if status in const.PAYMENT_STATUS_MAPPING['done']:
            self._set_done()
        elif status in const.PAYMENT_STATUS_MAPPING['pending']:
            self._set_pending(state_message=_(
                "seQura is reviewing the order; the payment will be confirmed shortly."
            ))
        elif status in const.PAYMENT_STATUS_MAPPING['cancel']:
            self._set_canceled()
        else:
            _logger.warning(
                "Received invalid seQura payment status (%s) for transaction %s.",
                status, self.reference,
            )
            self._set_error(_("seQura: Unknown payment status: %s", status))
