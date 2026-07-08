# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

{
    'name': "Payment Provider: seQura",
    'version': '19.0.1.0.3',
    'category': 'Accounting/Payment Providers',
    'sequence': 350,
    'summary': "Pago flexible con seQura: fracciona, divide o paga después.",
    'description': " ",  # Non-empty string to avoid loading the README file.
    'author': "Makeadito",
    'license': 'LGPL-3',
    'depends': ['payment'],
    'data': [
        'views/payment_sequra_templates.xml',
        'views/payment_provider_views.xml',

        'data/payment_method_data.xml',
        'data/payment_provider_data.xml',
    ],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'installable': True,
}
