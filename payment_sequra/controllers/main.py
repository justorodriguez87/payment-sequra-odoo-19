# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

import pprint

from markupsafe import Markup
from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger


_logger = get_payment_logger(__name__)


class SequraController(http.Controller):
    _checkout_url = '/payment/sequra/checkout'
    _return_url = '/payment/sequra/return'
    _webhook_url = '/payment/sequra/webhook'

    @http.route(
        _checkout_url, type='http', auth='public', methods=['POST'], csrf=False, website=True,
        save_session=False, sitemap=False,
    )
    def sequra_checkout(self, reference=None, access_token=None, **kwargs):
        """Start the seQura solicitation and render the identification form.

        The generic redirect form posts here instead of posting to seQura directly:
        seQura's checkout is an embedded HTML/JS form fetched from its API, not a
        hosted redirect page.

        :param str reference: The reference of the transaction.
        :param str access_token: The access token used to verify the authenticity of
                                 the redirection.
        """
        tx_sudo = self._sequra_get_tx_from_reference(reference)
        if not payment_utils.check_access_token(access_token, reference):
            raise Forbidden()

        try:
            form_html = tx_sudo._sequra_start_checkout()
        except ValidationError as error:
            return request.render('payment_sequra.checkout_error', {
                'error_message': str(error),
            })

        return request.render('payment_sequra.checkout', {
            'tx': tx_sudo,
            'sequra_form': Markup(form_html),
        })

    @http.route(
        _return_url, type='http', auth='public', methods=['GET'], csrf=False,
        save_session=False, sitemap=False,
    )
    def sequra_return_from_checkout(self, **data):
        """Handle the shopper's redirection after completing the seQura form.

        The transaction state is driven by the IPN webhook; this route only brings
        the shopper back to the generic payment status page.
        """
        _logger.info("Shopper returned from seQura with data:\n%s", pprint.pformat(data))
        return request.redirect('/payment/status')

    @http.route(
        _webhook_url, type='http', auth='public', methods=['POST'], csrf=False,
        save_session=False, sitemap=False,
    )
    def sequra_webhook(self, **data):
        """Process the IPN sent by seQura.

        On an approved event, the order must be confirmed back on seQura's API (PUT on
        the order URL) before marking the transaction as done. seQura retries the IPN
        if the response is not a 2xx.

        :param dict data: The IPN payload, including the echoed notification
                          parameters (`reference` and `signature`).
        :return: An empty 'OK' response to acknowledge the notification.
        """
        _logger.info("Received seQura IPN with data:\n%s", pprint.pformat(data))

        reference = data.get('reference') or data.get('order_ref_1')
        tx_sudo = self._sequra_get_tx_from_reference(reference)
        self._sequra_verify_signature(data, tx_sudo)

        status = (data.get('sq_state') or data.get('event') or 'approved').lower()
        if status == 'approved':
            response = tx_sudo._sequra_confirm_order()
            if response.status_code == 409:
                # The cart changed between the solicitation and the confirmation:
                # answer 410 so that seQura releases/cancels the order.
                _logger.warning(
                    "seQura reported a cart mismatch on confirmation of %s.", reference
                )
                return request.make_response('Cart mismatch', status=410)
            if not 200 <= response.status_code < 300:
                # Let seQura retry the IPN later.
                _logger.error(
                    "seQura order confirmation failed for %s (HTTP %s).",
                    reference, response.status_code,
                )
                return request.make_response('Confirmation failed', status=500)

        tx_sudo._process('sequra', data)
        return request.make_response('OK', status=200)

    # === HELPERS === #

    @staticmethod
    def _sequra_get_tx_from_reference(reference):
        """Find the seQura transaction matching the reference.

        :param str reference: The transaction reference.
        :return: The transaction, in sudo mode.
        :rtype: payment.transaction
        :raise ValidationError: If no transaction matches the reference.
        """
        tx_sudo = request.env['payment.transaction'].sudo().search([
            ('reference', '=', reference),
            ('provider_code', '=', 'sequra'),
        ], limit=1)
        if not tx_sudo:
            raise ValidationError(
                _("seQura: No transaction found matching reference %s.", reference)
            )
        return tx_sudo

    @staticmethod
    def _sequra_verify_signature(data, tx_sudo):
        """Check that the echoed signature matches the expected one.

        The signature is generated with the database secret when the order payload is
        built (`notification_parameters`) and echoed back by seQura in the IPN.

        :param dict data: The IPN payload.
        :param payment.transaction tx_sudo: The transaction matching the IPN.
        :return: None
        :raise Forbidden: If the signatures don't match.
        """
        received_signature = data.get('signature')
        if not received_signature or not payment_utils.check_access_token(
            received_signature, tx_sudo.reference
        ):
            _logger.warning(
                "Received seQura IPN with missing or invalid signature for %s.",
                tx_sudo.reference,
            )
            raise Forbidden()
