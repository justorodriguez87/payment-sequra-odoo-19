# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

import requests

from odoo import _, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.payment.logging import get_payment_logger
from odoo.addons.payment_sequra import const


_logger = get_payment_logger(__name__)


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('sequra', "seQura")], ondelete={'sequra': 'set default'}
    )
    sequra_username = fields.Char(
        string="seQura Username",
        help="El usuario proporcionado por seQura en el onboarding.",
        required_if_provider='sequra',
        copy=False,
    )
    sequra_password = fields.Char(
        string="seQura Password",
        help="La contraseña de la API proporcionada por seQura.",
        required_if_provider='sequra',
        copy=False,
        groups='base.group_system',
    )
    sequra_merchant_ref = fields.Char(
        string="seQura Merchant Reference",
        help="La referencia de comercio (merchant id) proporcionada por seQura, "
             "p. ej. 'makeadito'.",
        required_if_provider='sequra',
        copy=False,
    )
    sequra_product_code = fields.Char(
        string="seQura Product Code",
        help="Opcional. Fuerza un producto concreto de seQura en el checkout "
             "(p. ej. 'pp3' fracciona, 'i1' paga después, 'sp1' divide). "
             "Déjalo vacío para mostrar todos los productos contratados.",
        default='pp3',
        copy=False,
    )

    # === COMPUTE METHODS === #

    def _get_supported_currencies(self):
        """Override of `payment` to return EUR as the only supported currency."""
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'sequra':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    # === CRUD METHODS === #

    def _get_default_payment_method_codes(self):
        """Override of `payment` to return the default payment method codes."""
        self.ensure_one()
        if self.code != 'sequra':
            return super()._get_default_payment_method_codes()
        return const.DEFAULT_PAYMENT_METHOD_CODES

    # === BUSINESS METHODS === #

    def _sequra_get_api_url(self):
        """Return the base URL of the seQura API for this provider's state.

        :return: The API base URL.
        :rtype: str
        """
        self.ensure_one()
        if self.state == 'enabled':
            return const.API_URLS['production']
        return const.API_URLS['test']

    def _sequra_make_request(
        self, endpoint, method='POST', json_payload=None, headers=None, reference=None
    ):
        """Send a request to the seQura API and return the raw response.

        seQura's order flow relies on HTTP status codes and the `Location` response
        header (a 204 on order solicitation returns the order URL in `Location`), so
        this helper returns the raw `requests.Response` instead of parsed content.

        :param str endpoint: The endpoint to reach. Either a path (e.g. '/orders') or a
                             full URL (e.g. the order `Location` returned by seQura).
        :param str method: The HTTP method of the request.
        :param dict json_payload: The JSON payload of the request.
        :param dict headers: Optional headers overriding the defaults.
        :param str reference: The reference of the transaction, for logging.
        :return: The raw response.
        :rtype: requests.Response
        :raise ValidationError: If the connection to seQura could not be established.
        """
        self.ensure_one()

        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = self._sequra_get_api_url() + endpoint
        headers = headers or {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        auth = (self.sequra_username, self.sudo().sequra_password)

        self._log_request(method, url, json_payload, reference=reference)
        try:
            response = requests.request(
                method, url, json=json_payload, headers=headers, auth=auth, timeout=20
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            _logger.exception("Unable to reach seQura endpoint %s", url)
            raise ValidationError(
                _("seQura: Could not establish the connection to the payment provider.")
            )
        self._log_response(response, reference=reference)
        return response
