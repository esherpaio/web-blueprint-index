from flask import abort, make_response, redirect
from web.app.urls import url_for
from web.optimizer import optimizer
from werkzeug import Response

from bp_index import index_bp
from bp_index.sitemap import SitemapKind, SitemapService


@index_bp.route("/sitemap.xml")
@optimizer.cache
def sitemap() -> Response:
    xml = SitemapService().render_index()
    if xml is None:
        abort(404)
    return _xml_response(xml)


@index_bp.route("/sitemap-<string:group>.xml", defaults={"part": None})
@index_bp.route("/sitemap-<string:group>-<int:part>.xml")
@optimizer.cache
def sitemap_group(group: str, part: int | None) -> Response:
    if part is None:
        return redirect(
            url_for("index.sitemap_group", group=group, part=1),
            code=301,
        )
    xml = SitemapService().render_part(group, part, SitemapKind.PAGES)
    if xml is None:
        abort(404)
    return _xml_response(xml)


@index_bp.route("/sitemap-<string:group>-images.xml", defaults={"part": None})
@index_bp.route("/sitemap-<string:group>-images-<int:part>.xml")
@optimizer.cache
def sitemap_group_images(group: str, part: int | None) -> Response:
    if part is None:
        return redirect(
            url_for("index.sitemap_group_images", group=group, part=1),
            code=301,
        )
    xml = SitemapService().render_part(group, part, SitemapKind.IMAGES)
    if xml is None:
        abort(404)
    return _xml_response(xml)


def _xml_response(xml: bytes) -> Response:
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response
