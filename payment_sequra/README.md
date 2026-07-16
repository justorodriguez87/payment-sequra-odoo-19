# Payment Provider: seQura — Odoo 19

Módulo de pago seQura para Odoo 19 Community, reescrito desde cero sobre el
framework `payment.provider` de Odoo 19, partiendo de la lógica de API del
conector oficial de seQura para Odoo 12 (`sequra/Conector-Odoo-Sequra-Payment`).

## Flujo de pago

1. El cliente elige seQura en el checkout. El formulario de redirección genérico
   de Odoo hace POST a `/payment/sequra/checkout` (con firma `access_token`).
2. El controlador inicia la **solicitud** contra la API de seQura
   (`POST /orders`, estado `""`), guarda la URL del pedido (header `Location`)
   en la transacción y la pasa a estado *pendiente*.
3. Se recupera el **formulario de identificación** (`GET {location}/form_v2`)
   y se renderiza embebido en una página del propio sitio.
4. El cliente completa el proceso en el formulario de seQura. seQura envía el
   **IPN** a `/payment/sequra/webhook` con los `notification_parameters`
   (referencia + firma HMAC generada con el secreto de la base de datos).
5. Si el estado es `approved`, el módulo **confirma** el pedido en seQura
   (`PUT {location}`, estado `confirmed`). seQura revalida los totales del
   carrito. Con respuesta 2xx la transacción pasa a *done* y Odoo confirma el
   pedido de venta por el flujo estándar de post-procesado.
   - Respuesta 409 de seQura (carrito cambiado) → se responde 410 para que
     seQura libere el pedido.
   - Otros errores → se responde 500 para que seQura reintente el IPN.
6. El shopper vuelve por `return_url` a `/payment/status` (página estándar).

## Instalación (Docker, shop.makeadito.com)

```bash
# 1. Copiar el módulo al directorio de addons montado en el contenedor
scp -r payment_sequra tu-vps:/ruta/a/odoo/addons/

# 2. Reiniciar y actualizar la lista de apps + instalar
docker compose restart odoo
docker compose exec odoo odoo -d NOMBRE_BD -i payment_sequra --stop-after-init
docker compose restart odoo
```

O desde la interfaz: Apps → Actualizar lista de aplicaciones → buscar "seQura"
→ Instalar.

## Configuración

1. `Sitio web → Configuración → Proveedores de pago → seQura`.
2. Pestaña **Credenciales**: Username, Password y Merchant Reference que te dio
   seQura en el onboarding.
3. **Product Code** (opcional): fuerza un producto concreto (`pp3` fracciona,
   `i1` paga después, `sp1` divide). Vacío = seQura muestra todos los
   productos contratados en el formulario.
4. Estado **Modo de prueba** → usa `sandbox.sequrapi.com`.
   Estado **Activado** → usa `live.sequrapi.com`.
5. En la pestaña Configuración puedes fijar importe máximo, países, etc.
   (seQura opera en ES/PT/FR/IT y solo en EUR; el módulo ya filtra la moneda).

## Requisito de red (importante en tu setup)

seQura debe poder alcanzar `https://shop.makeadito.com/payment/sequra/webhook`
(IPN) **por POST**. Verifica que:

- Cloudflare no bloquee ni desafíe (challenge) esos POST: crea una WAF rule /
  Configuration Rule para la ruta `/payment/sequra/*` con Security Level bajo
  y sin Browser Integrity Check.
- El proxy de Plesk/nginx pase el POST al contenedor de Odoo (misma regla que
  el resto del sitio; no necesita nada especial, a diferencia de /websocket).

## Pruebas en sandbox

1. Proveedor en "Modo de prueba" con credenciales de sandbox.
2. Haz un pedido de prueba en la tienda; en el formulario de seQura usa los
   datos de prueba de su documentación de onboarding.
3. Comprueba en `Sitio web → Configuración → Proveedores de pago → seQura →
   pestaña de transacciones` (o en Ajustes técnicos → Transacciones de pago)
   que la transacción pasa: borrador → pendiente → hecho.
4. El log del contenedor muestra las peticiones/respuestas a seQura
   (logger `odoo.addons.payment`).

## Notas de diseño y limitaciones

- **Sin reembolsos desde Odoo** (v1). Los reembolsos se gestionan desde el
  portal de seQura. Se puede añadir después con `support_refund` y el endpoint
  de refunds de la API.
- **Sin widgets promocionales** en ficha de producto (teaser "desde X €/mes").
  El módulo viejo los tenía; se pueden añadir después como snippet del website
  con el JS de seQura (`sequra.assetsBaseUrl`).
- El importe del IPN no se valida en Odoo (`_extract_amount_data` → `None`)
  porque seQura no lo envía en el IPN y ya revalida los totales del carrito en
  el `PUT` de confirmación, que es la fuente de verdad.
- Si la transacción no viene de un pedido de venta (pago de factura desde el
  portal, enlace de pago), el carrito se envía como un único item por el total.
- El item de **ajuste** (`adjustment`) garantiza que la suma de items siempre
  cuadre con `order_total_with_tax` (redondeos, pagos parciales/anticipos).
