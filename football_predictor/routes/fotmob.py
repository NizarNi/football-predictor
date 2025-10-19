from __future__ import annotations

from flask import Blueprint, Response

bp = Blueprint("fotmob_page", __name__, url_prefix="/fotmob")


@bp.get("/")
def index() -> Response:
    """Return a minimal FotMob placeholder page."""
    # Minimal stub page (we’ll replace with templates in T2.2)
    html = """
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>FotMob (beta)</title>
        <style>
          body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 20px; }
          .container { max-width: 960px; margin: 0 auto; }
          .muted { color: #666; }
          .card { border: 1px solid #eee; border-radius: 10px; padding: 16px; margin: 12px 0; }
        </style>
      </head>
      <body>
        <div class="container">
          <h1>FotMob feed (beta)</h1>
          <p class="muted">This is a placeholder. Infinite scroll + cards will arrive in T3/T4.</p>
          <div class="card">
            <strong>API endpoints:</strong>
            <ul>
              <li><code>GET /api/fotmob/feed</code> — returns empty feed stub</li>
              <li><code>GET /api/fotmob/match/&lt;id&gt;</code> — returns empty match stub</li>
            </ul>
          </div>
        </div>
      </body>
    </html>
    """
    return Response(html, mimetype="text/html")
