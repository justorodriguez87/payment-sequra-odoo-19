# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

# seQura API base URLs. See https://docs.sequrapi.com/.
API_URLS = {
    'production': 'https://live.sequrapi.com',
    'test': 'https://sandbox.sequrapi.com',
}

# The codes of the payment methods to activate when seQura is activated.
DEFAULT_PAYMENT_METHOD_CODES = {
    'sequra',
}

# seQura only processes payments in EUR.
SUPPORTED_CURRENCIES = [
    'EUR',
]

# Countries where seQura operates.
SUPPORTED_COUNTRIES = [
    'ES',
    'PT',
    'FR',
    'IT',
]

# Mapping of seQura IPN/order states to transaction handling.
# `approved`: seQura approved the financing; the order must be confirmed with a PUT.
# `needs_review`: seQura is manually reviewing the order; keep the transaction pending.
# `cancelled`: the shopper or seQura cancelled the process.
PAYMENT_STATUS_MAPPING = {
    'pending': ('needs_review', 'on_hold'),
    'done': ('approved',),
    'cancel': ('cancelled', 'canceled'),
}
