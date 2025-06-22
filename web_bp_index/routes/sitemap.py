import itertools
from typing import Type

from flask import Response, current_app, make_response, render_template
from sqlalchemy.orm import joinedload
from web.app.routing import has_argument, is_endpoint
from web.app.sitemap import Sitemap, SitemapUrl
from web.cache import cache
from web.database import conn
from web.database.model import Article, Category, Sku
from web.locale import gen_locale
from web.utils.modifiers import text_to_xml

from web_bp_index import index_bp


@index_bp.route("/sitemap.xml")
def sitemap() -> Response:
    sitemaps = []
    for rule in current_app.url_map.iter_rules():
        if rule.endpoint and rule.endpoint.startswith("index.sitemap_"):
            sitemaps.append(Sitemap(rule.endpoint))
    template = render_template("sitemap_index.xml", sitemaps=sitemaps)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response


@index_bp.route("/sitemap-pages.xml")
def sitemap_pages() -> Response:
    iter_args = (
        [x for x in cache.countries if x.in_sitemap],
        [x for x in cache.languages if x.in_sitemap],
    )

    urls = []
    for route in cache.routes:
        if (
            route.is_collection
            or not route.in_sitemap
            or not is_endpoint(route.endpoint)
        ):
            continue
        if has_argument(route.endpoint, "_locale"):
            for country, language in itertools.product(*iter_args):
                locale = gen_locale(language.code, country.code)
                urls.append(SitemapUrl(route.endpoint, _locale=locale))
        else:
            urls.append(SitemapUrl(route.endpoint))

    template = render_template("sitemap.xml", urls=urls)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response


@index_bp.route("/sitemap-products.xml")
def sitemap_products() -> Response:
    return _generate_sitemap(Sku)


@index_bp.route("/sitemap-articles.xml")
def sitemap_articles() -> Response:
    return _generate_sitemap(Article)


@index_bp.route("/sitemap-categories.xml")
def sitemap_categories() -> Response:
    return _generate_sitemap(Category)


def _generate_sitemap(model: Type[Sku | Article | Category]) -> Response:
    with conn.begin() as s:
        objs = (
            s.query(model)
            .options(joinedload(model.route))
            .filter_by(is_deleted=False)
            .order_by(model.slug)
            .all()
        )

    iter_args = (
        [x for x in cache.countries if x.in_sitemap],
        [x for x in cache.languages if x.in_sitemap],
    )

    urls = []
    for obj in objs:
        if (
            not obj.route
            or not obj.route.is_collection
            or not is_endpoint(obj.route.endpoint)
        ):
            continue
        endpoint = obj.route.endpoint
        if has_argument(endpoint, "_locale"):
            for country, language in itertools.product(*iter_args):
                locale = gen_locale(language.code, country.code)
                urls.append(SitemapUrl(endpoint, _locale=locale, slug=obj.slug))
        else:
            urls.append(SitemapUrl(endpoint, slug=obj.slug))

    template = render_template("sitemap.xml", urls=urls)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response
