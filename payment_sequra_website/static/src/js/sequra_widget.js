/* Part of payment_sequra. See LICENSE file for full copyright and licensing details. */
(function () {
    'use strict';

    function parsePriceToCents(text, config) {
        if (!text) {
            return null;
        }
        var cleaned = text.replace(/[^\d.,-]/g, '');
        if (!cleaned) {
            return null;
        }
        var thousand = config.thousandSeparator || '.';
        var decimal = config.decimalSeparator || ',';
        cleaned = cleaned.split(thousand).join('');
        if (decimal !== '.') {
            cleaned = cleaned.replace(decimal, '.');
        }
        var value = parseFloat(cleaned);
        if (isNaN(value)) {
            return null;
        }
        return Math.round(value * 100);
    }

    function refreshSequra() {
        if (window.Sequra && typeof window.Sequra.refreshComponents === 'function') {
            window.Sequra.refreshComponents();
        }
    }

    function loadSequraLibrary(config) {
        if (window.SequraConfiguration) {
            return; // Already loaded on this page.
        }
        var sequraConfigParams = {
            merchant: config.merchant,
            assetKey: config.assetKey,
            products: config.products,
            scriptUri: config.scriptUri,
            decimalSeparator: config.decimalSeparator,
            thousandSeparator: config.thousandSeparator,
            locale: config.locale,
            currency: config.currency,
        };
        /* Official seQura async loader snippet. */
        (function (i, s, o, g, r, a, m) {
            i['SequraConfiguration'] = g;
            i['SequraOnLoad'] = [];
            i[r] = i[r] || {};
            i[r][a] = function (callback) { i['SequraOnLoad'].push(callback); };
            (a = s.createElement(o)), (m = s.getElementsByTagName(o)[0]);
            a.async = 1;
            a.src = g.scriptUri;
            m.parentNode.insertBefore(a, m);
        })(window, document, 'script', sequraConfigParams, 'Sequra', 'onLoad');
    }

    function setWidgetsAmount(root, cents) {
        var widgets = root.querySelectorAll('.sequra-promotion-widget');
        var changed = false;
        widgets.forEach(function (widget) {
            if (widget.getAttribute('data-amount') !== String(cents)) {
                widget.setAttribute('data-amount', String(cents));
                changed = true;
            }
        });
        return changed;
    }

    /* --- Product page: keep the widget amount in sync with the variant price. --- */
    function initProductPage(config) {
        var priceContainer = document.querySelector('.product_price');
        if (!priceContainer) {
            return;
        }
        var sync = function () {
            var priceEl = document.querySelector('.product_price .oe_price');
            if (!priceEl) {
                return;
            }
            var cents = parsePriceToCents(priceEl.textContent, config);
            if (cents !== null && setWidgetsAmount(document, cents)) {
                refreshSequra();
            }
        };
        if (window.MutationObserver) {
            new MutationObserver(sync).observe(priceContainer, {
                childList: true,
                subtree: true,
                characterData: true,
            });
        }
        if (window.Sequra && typeof window.Sequra.onLoad === 'function') {
            window.Sequra.onLoad(sync);
        }
    }

    /* --- Cart page: survive Odoo's summary re-renders and follow the total. --- */
    function initCartPage(config, widgetHtml) {
        var totalCard = document.querySelector('.o_total_card');
        if (!totalCard) {
            return;
        }
        var syncing = false;
        var sync = function () {
            if (syncing) {
                return;
            }
            syncing = true;
            try {
                var cartTotalEl = document.querySelector('.o_cart_total');
                if (!cartTotalEl) {
                    return; // Cart emptied.
                }
                var wrapper = document.querySelector('.o_sequra_cart_widget');
                if (!wrapper) {
                    /* The summary was re-rendered by Odoo and our widget was wiped:
                       re-insert it right after the totals block. */
                    cartTotalEl.insertAdjacentHTML('afterend', widgetHtml);
                    wrapper = document.querySelector('.o_sequra_cart_widget');
                }
                var totalRow = document.querySelector(
                    'tr[name="o_order_total"] .oe_currency_value'
                );
                if (totalRow) {
                    var cents = parsePriceToCents(totalRow.textContent, config);
                    if (cents !== null) {
                        setWidgetsAmount(wrapper, cents);
                    }
                }
                refreshSequra();
            } finally {
                syncing = false;
            }
        };
        if (window.MutationObserver) {
            var timer = null;
            new MutationObserver(function () {
                clearTimeout(timer);
                timer = setTimeout(sync, 150); // Debounce bursts of DOM patches.
            }).observe(totalCard, { childList: true, subtree: true, characterData: true });
        }
        if (window.Sequra && typeof window.Sequra.onLoad === 'function') {
            window.Sequra.onLoad(sync);
        }
    }

    function init() {
        var wrapper = document.querySelector('.o_sequra_widget_wrapper');
        if (!wrapper) {
            return;
        }
        var config;
        try {
            config = JSON.parse(wrapper.getAttribute('data-sequra-config'));
        } catch (e) {
            return;
        }
        if (!config || !config.merchant || !config.assetKey) {
            return;
        }

        loadSequraLibrary(config);
        initProductPage(config);

        var cartWrapper = document.querySelector('.o_sequra_cart_widget');
        if (cartWrapper) {
            initCartPage(config, cartWrapper.outerHTML);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
