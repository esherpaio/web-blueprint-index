import itertools

from flask import Response, abort, make_response, render_template
from web.app.routing import has_argument, is_endpoint
from web.cache import cache
from web.locale import gen_locale
from web.utils.modifiers import text_to_xml

from bp_index import index_bp
from bp_index._models import Sitemap, SitemapUrl
from bp_index._utils import get_latest_date


@index_bp.route("/sitemap.xml")
def sitemap() -> Response:
    sitemaps = []
    for endpoint in ["index.sitemap_pages"]:
        urls = _get_sitemap_urls()
        if urls:
            updated_at = get_latest_date(*(url._updated_at for url in urls))
            sitemaps.append(Sitemap(endpoint, updated_at))
    if not sitemaps:
        abort(404)

    template = render_template("sitemap_index.xml", sitemaps=sitemaps)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response


@index_bp.route("/sitemap-pages.xml")
def sitemap_pages() -> Response:
    urls = _get_sitemap_urls()
    if not urls:
        abort(404)
    return _generate_sitemap(urls)


def _get_sitemap_urls() -> list[SitemapUrl]:
    locale_iter_args = (
        [x for x in cache.countries if x.in_sitemap],
        [x for x in cache.languages if x.in_sitemap],
    )

    urls = []
    for route in cache.routes:
        if not route.in_sitemap or not is_endpoint(route.endpoint):
            continue
        if route.is_collection and (
            not route.sitemap_query_key or not route.sitemap_query_values
        ):
            continue

        # Collect locale arguments
        if has_argument(route.endpoint, "_locale"):
            locale_args = [
                {"_locale": gen_locale(lang.code, country.code)}
                for country, lang in itertools.product(*locale_iter_args)
            ]
        else:
            locale_args = [{}]

        # Collect query arguments
        if route.is_collection:
            query_args = [
                {route.sitemap_query_key: v} for v in route.sitemap_query_values
            ]
        else:
            query_args = [{}]

        # Build sitemap URLs
        updated_at = get_latest_date(route.updated_at, route.created_at)
        for la, qa in itertools.product(locale_args, query_args):
            urls.append(SitemapUrl(route.endpoint, updated_at=updated_at, **la, **qa))

    return urls


def _generate_sitemap(urls: list[SitemapUrl]) -> Response:
    template = render_template("sitemap.xml", urls=urls)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response
