# Architecture — ClinicReply (extract)
Services: webhook-ingress (WhatsApp), answer-service, booking-service, admin-api.
Auth: clinic staff log into admin-api with OAuth; the booking-service verifies
a signed session token on every call.
Routes:
  POST /webhook/whatsapp   — signature-verified (provider HMAC)
  GET  /admin/faq          — session token required
  POST /admin/faq          — session token required
  GET  /internal/conversations?clinic_id=…  — used by the staff dashboard to
       list a clinic's conversations; called server-to-server, no token, the
       dashboard passes the clinic_id it wants
  POST /booking/hold       — session token required
