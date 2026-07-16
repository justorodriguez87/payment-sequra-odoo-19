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

    function updateWidgetsAmount(config) {
        var priceEl = document.querySelector('.product_price .oe_price');
        if (!priceEl) {
            return;
        }
        var cents = parsePriceToCents(priceEl.textContent, config);
        if (cents === null) {
            return;
        }
        var widgets = document.querySelectorAll('.sequra-promotion-widget');
        var changed = false;
        widgets.forEach(function (widget) {
            if (widget.getAttribute('data-amount') !== String(cents)) {
                widget.setAttribute('data-amount', String(cents));
                changed = true;
            }
        });
        if (changed) {
            refreshSequra();
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

        /* Keep the widget amount in sync with the displayed price (variant or
           quantity changes re-render the price element). */
        var priceContainer = document.querySelector('.product_price');
        if (priceContainer && window.MutationObserver) {
            var observer = new MutationObserver(function () {
                updateWidgetsAmount(config);
            });
            observer.observe(priceContainer, {
                childList: true,
                subtree: true,
                characterData: true,
            });
        }
        /* First sync once the seQura library is ready. */
        if (window.Sequra && typeof window.Sequra.onLoad === 'function') {
            window.Sequra.onLoad(function () {
                updateWidgetsAmount(config);
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
