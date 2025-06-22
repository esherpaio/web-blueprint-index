import os

from flask import Response, make_response, render_template
from web.app.urls import url_for

from web_bp_index import index_bp


@index_bp.route("/robots.txt")
def robots() -> Response:
    template = render_template(
        "robots.txt",
        disallow_urls=["/api/*", "/webhook/*", "/user/*", "/admin/*"],
        sitemap_url=url_for("index.sitemap", _external=True),
    )
    text = os.linesep.join([x for x in template.splitlines() if x])
    response = make_response(text)
    response.headers["Content-Type"] = "text/plain"
    return response
