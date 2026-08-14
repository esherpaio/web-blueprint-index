import itertools
from datetime import datetime

from flask import Response, abort, make_response, render_template
from sqlalchemy import true
from sqlalchemy.orm import joinedload
from web.app.routing import has_argument, is_endpoint
from web.app.urls import url_for
from web.cache import cache
from web.database import conn
from web.database.model import AppRoute, SitemapLocation
from web.locale import gen_locale
from web.utils.modifiers import text_to_xml

from bp_index import index_bp
from bp_index.models import Sitemap


@index_bp.route("/sitemap.xml")
def sitemap() -> Response:
    group_lastmods: dict[str, datetime] = {}
    for location in _get_sitemap_location_rows():
        group = location.route.sitemap_group
        group_lastmods[group] = max(
            group_lastmods.get(group, location.lastmod),
            location.lastmod,
        )

    sitemaps = [
        Sitemap("index.sitemap_group", lastmod, group=group)
        for group, lastmod in sorted(group_lastmods.items())
    ]
    if not sitemaps:
        abort(404)

    template = render_template("sitemap_index.xml", sitemaps=sitemaps)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response


@index_bp.route("/sitemap-<string:group>.xml")
def sitemap_group(group: str) -> Response:
    locations = _get_sitemap_locations(group)
    if not locations:
        abort(404)
    return _generate_sitemap(locations)


def _get_sitemap_location_rows(group: str | None = None) -> list[SitemapLocation]:
    with conn.begin() as s:
        query = (
            s.query(SitemapLocation)
            .join(SitemapLocation.route)
            .options(joinedload(SitemapLocation.route))
            .filter(AppRoute.in_sitemap == true())
        )
        if group is not None:
            query = query.filter(AppRoute.sitemap_group == group)
        sitemap_locations = query.order_by(
            AppRoute.sitemap_group,
            SitemapLocation.route_id,
            SitemapLocation.id,
        ).all()

    return [
        location
        for location in sitemap_locations
        if is_endpoint(location.route.endpoint)
    ]


def _get_sitemap_locations(group: str) -> list[tuple[SitemapLocation, str]]:
    locale_iter_args = (
        [x for x in cache.countries if x.in_sitemap],
        [x for x in cache.languages if x.in_sitemap],
    )

    locations = []
    for sitemap_location in _get_sitemap_location_rows(group):
        route = sitemap_location.route
        # Collect locale arguments
        if has_argument(route.endpoint, "_locale"):
            locale_args = [
                {"_locale": gen_locale(lang.code, country.code)}
                for country, lang in itertools.product(*locale_iter_args)
            ]
        else:
            locale_args = [{}]

        # Build sitemap locations
        for locale_args_ in locale_args:
            endpoint_args = sitemap_location.endpoint_args | locale_args_
            loc = url_for(route.endpoint, **endpoint_args, _external=True)
            locations.append((sitemap_location, loc))

    return locations


def _generate_sitemap(
    locations: list[tuple[SitemapLocation, str]],
) -> Response:
    template = render_template("sitemap.xml", locations=locations)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response
