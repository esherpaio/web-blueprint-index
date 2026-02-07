import itertools
from typing import Type

from flask import Response, abort, make_response, render_template
from sqlalchemy.orm import joinedload
from web.app.routing import has_argument, is_endpoint
from web.cache import cache
from web.database import conn
from web.database.model import Article, Category, Sku
from web.locale import gen_locale
from web.utils.modifiers import text_to_xml

from bp_index import index_bp
from bp_index._models import Sitemap, SitemapUrl
from bp_index._utils import get_latest_date


@index_bp.route("/sitemap.xml")
def sitemap() -> Response:
    sitemap_generators = {
        "index.sitemap_pages": _get_route_sitemap_urls,
        "index.sitemap_products": lambda: _get_related_route_sitemap_urls(Sku),
        "index.sitemap_articles": lambda: _get_related_route_sitemap_urls(Article),
        "index.sitemap_categories": lambda: _get_related_route_sitemap_urls(Category),
    }

    sitemaps = []
    for endpoint, generator in sitemap_generators.items():
        urls = generator()
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
    urls = _get_route_sitemap_urls()
    if not urls:
        abort(404)
    return _generate_sitemap(urls)


@index_bp.route("/sitemap-products.xml")
def sitemap_products() -> Response:
    urls = _get_related_route_sitemap_urls(Sku)
    if not urls:
        abort(404)
    return _generate_sitemap(urls)


@index_bp.route("/sitemap-articles.xml")
def sitemap_articles() -> Response:
    urls = _get_related_route_sitemap_urls(Article)
    if not urls:
        abort(404)
    return _generate_sitemap(urls)


@index_bp.route("/sitemap-categories.xml")
def sitemap_categories() -> Response:
    urls = _get_related_route_sitemap_urls(Category)
    if not urls:
        abort(404)
    return _generate_sitemap(urls)


def _get_route_sitemap_urls() -> list[SitemapUrl]:
    iter_args = (
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
        updated_at = get_latest_date(route.updated_at, route.created_at)
        if has_argument(route.endpoint, "_locale"):
            locale_args = [
                {"_locale": gen_locale(lang.code, country.code)}
                for country, lang in itertools.product(*iter_args)
            ]
        else:
            locale_args = [{}]
        if (
            route.is_collection
            and route.sitemap_query_key
            and route.sitemap_query_values
        ):
            query_args = [
                {route.sitemap_query_key: v} for v in route.sitemap_query_values
            ]
        else:
            query_args = [{}]
        for la, qa in itertools.product(locale_args, query_args):
            urls.append(SitemapUrl(route.endpoint, updated_at=updated_at, **la, **qa))

    return urls


def _get_related_route_sitemap_urls(
    model: Type[Sku | Article | Category],
) -> list[SitemapUrl]:
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
        updated_at = get_latest_date(
            obj.updated_at,
            obj.route.updated_at,
            obj.created_at,
            obj.route.created_at,
        )
        if has_argument(endpoint, "_locale"):
            locale_args = [
                {"_locale": gen_locale(lang.code, country.code)}
                for country, lang in itertools.product(*iter_args)
            ]
        else:
            locale_args = [{}]
        for la in locale_args:
            urls.append(
                SitemapUrl(endpoint, slug=obj.slug, updated_at=updated_at, **la)
            )
    return urls


def _generate_sitemap(urls: list[SitemapUrl]) -> Response:
    template = render_template("sitemap.xml", urls=urls)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response
