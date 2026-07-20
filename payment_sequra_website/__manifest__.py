# Part of payment_sequra. See LICENSE file for full copyright and licensing details.

{
    'name': "seQura: eCommerce Widgets & Restrictions",
    'version': '19.0.1.0.2',
    'category': 'Accounting/Payment Providers',
    'summary': "Widgets promocionales de seQura y exclusión de productos no financiables.",
    'description': " ",
    'author': "Makeadito",
    'license': 'LGPL-3',
    'depends': ['payment_sequra', 'website_sale'],
    'auto_install': True,
    'data': [
        'views/product_template_views.xml',
        'views/templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'payment_sequra_website/static/src/js/sequra_widget.js',
        ],
    },
    'installable': True,
}
