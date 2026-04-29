"""Analytics utilities for TheAssembly.

Provides GA4 + Microsoft Clarity tracking HTML injection and
a server-side GA4 Measurement Protocol event emitter.

All functions are safe to call when analytics is disabled (they
return empty strings / no-ops), so no call-site guarding is needed.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

_GA4_MP_ENDPOINT = "https://www.google-analytics.com/mp/collect"
_log = logging.getLogger(__name__)


def get_tracking_html(
    ga4_id: str,
    clarity_id: str,
    app_role: str = "",
    gym_status: str = "",
) -> str:
    """Return combined GA4 + Clarity <script> HTML for page-head injection.

    Returns an empty string when either ID is falsy so callers can
    unconditionally pass the result to ``st.components.v1.html``.

    Args:
        ga4_id: GA4 Measurement ID.
        clarity_id: Microsoft Clarity project ID.
        app_role: Optional role tag sent as a Clarity custom tag (e.g. "athlete").
        gym_status: Optional gym state tag for Clarity filtering (e.g. "open", "closed").
    """
    if not ga4_id or not clarity_id:
        return ""

    return f"""
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={ga4_id}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  // Resolve the real page URL even when this script runs inside a Streamlit
  // srcdoc iframe (where document.location is "about:srcdoc"). GA4 Realtime
  // requires a valid page_location to attribute active users correctly.
  var _pageUrl = (function() {{
    try {{ return window.top.location.href; }} catch(e) {{}}
    try {{ return window.parent.location.href; }} catch(e) {{}}
    return document.referrer || 'https://asm-athlete.streamlit.app/';
  }})();
  var _pageTitle = (function() {{
    try {{ return window.top.document.title; }} catch(e) {{}}
    return document.title || 'TheAssembly';
  }})();
  gtag('config', '{ga4_id}', {{
    'anonymize_ip': true,
    'allow_google_signals': true,
    'send_page_view': false,
    'page_location': _pageUrl
  }});
  // Emit an explicit page_view because auto pageview can be unreliable from
  // sandboxed iframe contexts.
  gtag('event', 'page_view', {{
    'page_location': _pageUrl,
    'page_referrer': document.referrer || undefined,
    'page_title': _pageTitle
  }});
</script>
<!-- Microsoft Clarity -->
<script type="text/javascript">
  (function(c,l,a,r,i,t,y){{
    c[a]=c[a]||function(){{(c[a].q=c[a].q||[]).push(arguments)}};
    t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
    y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
  }})(window,document,"clarity","script","{clarity_id}");
  // Custom tags let Clarity recordings be filtered by gym state and user role.
  if ("{app_role}")   {{ clarity("set", "app_role",   "{app_role}");  }}
  if ("{gym_status}") {{ clarity("set", "gym_status", "{gym_status}"); }}
</script>
"""


def fire_event(
    ga4_id: str,
    api_secret: str,
    event_name: str,
    params: dict[str, Any] | None = None,
    client_id: str = "streamlit-server",
) -> None:
    """Fire a GA4 Measurement Protocol event from the server side.

    Silently swallows all errors so analytics failures never surface to users.
    ``api_secret`` is the GA4 Measurement Protocol API secret; leave empty to
    skip (the function becomes a no-op).
    """
    if not ga4_id or not api_secret:
        return

    payload = json.dumps({
        "client_id": client_id,
        "events": [{"name": event_name, "params": params or {}}],
    }).encode()

    url = f"{_GA4_MP_ENDPOINT}?measurement_id={ga4_id}&api_secret={api_secret}"
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3):
            pass
    except Exception as exc:
        _log.debug("Analytics event %r failed: %s", event_name, exc)
