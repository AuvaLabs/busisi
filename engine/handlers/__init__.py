"""FastAPI handler app for grimoire (Phase 9).

Exposes the public mutating surface the static renderer can't serve:

  POST /api/subscribe          newsletter signup (double opt-in)
  GET  /confirm?token=…        confirm subscriber via email link
  GET  /unsubscribe?token=…    one-click unsubscribe
  POST /api/sponsor            inbound sponsor inquiry
  POST /api/tools/{slug}/calculate   per-vertical calculator runner

Reads stay on the static side — the renderer owns every public GET except
the two single-use confirm/unsubscribe links above. Caddy reverse-proxies
these prefixes to the loopback uvicorn process.
"""
