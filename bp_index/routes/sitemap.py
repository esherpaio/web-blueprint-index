import itertools
from collections.abc import Collection
from datetime import datetime

from flask import Response, abort, current_app, make_response, render_template
from sqlalchemy import func, true
from sqlalchemy.orm import joinedload, selectinload
from web.app.urls import url_for
from web.cache import cache
from web.database import conn
from web.database.model import AppRoute, SitemapImageMode, SitemapLocation
from web.locale import gen_locale
from web.utils.modifiers import text_to_xml

from bp_index import index_bp
from bp_index.models import Sitemap, SitemapAlternate, SitemapEntry

#
# Routes
#


@index_bp.route("/sitemap.xml")
def sitemap() -> Response:
    locale_variants = _get_locale_variants()
    excluded_endpoints = _get_localized_endpoints() if not locale_variants else set()
    sitemaps: list[Sitemap] = [
        Sitemap(
            loc=url_for("index.sitemap_group", group=group, _external=True),
            lastmod=lastmod.strftime("%Y-%m-%d"),
        )
        for group, lastmod in _get_sitemap_group_lastmods(
            excluded_endpoints=excluded_endpoints
        )
    ]

    sitemaps.extend(
        Sitemap(
            loc=url_for("index.sitemap_group_images", group=group, _external=True),
            lastmod=lastmod.strftime("%Y-%m-%d"),
        )
        for group, lastmod in _get_sitemap_group_lastmods(image_only=True)
    )

    if not sitemaps:
        abort(404)
    template = render_template("sitemap_index.xml", sitemaps=sitemaps)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response


@index_bp.route("/sitemap-<string:group>.xml")
def sitemap_group(group: str) -> Response:
    entries = _get_sitemap_entries(group)
    if not entries:
        abort(404)
    return _generate_sitemap(entries)


@index_bp.route("/sitemap-<string:group>-images.xml")
def sitemap_group_images(group: str) -> Response:
    entries = _get_sitemap_entries(group, image_only=True)
    if not entries:
        abort(404)
    return _generate_sitemap(entries)


def _generate_sitemap(entries: list[SitemapEntry]) -> Response:
    template = render_template("sitemap.xml", entries=entries)
    response = make_response(text_to_xml(template))
    response.headers["Content-Type"] = "application/xml"
    return response


#
# Helpers
#


def _get_sitemap_group_lastmods(
    *,
    image_only: bool = False,
    excluded_endpoints: Collection[str] = (),
) -> list[tuple[str, datetime]]:
    with conn.begin() as s:
        query = (
            s.query(AppRoute.sitemap_group, func.max(SitemapLocation.lastmod))
            .select_from(SitemapLocation)
            .join(SitemapLocation.route)
            .filter(AppRoute.in_sitemap == true())
        )
        if image_only:
            query = query.filter(
                AppRoute.sitemap_image_mode == SitemapImageMode.SEPARATE,
                SitemapLocation.images.any(),
            )
        if excluded_endpoints:
            query = query.filter(AppRoute.endpoint.notin_(excluded_endpoints))
        rows = (
            query.group_by(AppRoute.sitemap_group)
            .order_by(AppRoute.sitemap_group)
            .all()
        )
    return [(group, lastmod) for group, lastmod in rows]


def _get_sitemap_locations(
    group: str,
    image_only: bool = False,
) -> list[SitemapLocation]:
    with conn.begin() as s:
        query = (
            s.query(SitemapLocation)
            .join(SitemapLocation.route)
            .options(
                joinedload(SitemapLocation.route),
                selectinload(SitemapLocation.images),
            )
            .filter(
                AppRoute.in_sitemap == true(),
                AppRoute.sitemap_group == group,
            )
        )
        if image_only:
            query = query.filter(
                AppRoute.sitemap_image_mode == SitemapImageMode.SEPARATE,
                SitemapLocation.images.any(),
            )
        return query.order_by(SitemapLocation.route_id, SitemapLocation.id).all()


def _get_sitemap_entries(
    group: str,
    image_only: bool = False,
) -> list[SitemapEntry]:
    sitemap_locations = _get_sitemap_locations(group, image_only=image_only)
    locale_variants = tuple() if image_only else _get_locale_variants()
    localized_endpoints = _get_localized_endpoints()

    entries: list[SitemapEntry] = []
    for sitemap_location in sitemap_locations:
        route = sitemap_location.route
        is_localized = route.endpoint in localized_endpoints
        endpoint_arg_variants: tuple[dict[str, str], ...]
        if is_localized:
            if image_only:
                endpoint_arg_variants = ({"_locale": gen_locale()},)
            elif locale_variants:
                endpoint_arg_variants = tuple(
                    endpoint_args for endpoint_args, _ in locale_variants
                )
            else:
                continue
        else:
            endpoint_arg_variants = ({},)

        alternates = (
            _get_sitemap_alternates(sitemap_location, locale_variants)
            if not image_only and is_localized
            else tuple()
        )
        include_images = (
            image_only or route.sitemap_image_mode == SitemapImageMode.COMBINED
        )
        image_locs = (
            tuple(image.loc for image in sitemap_location.images)
            if include_images
            else tuple()
        )
        lastmod = sitemap_location.lastmod.strftime("%Y-%m-%d")
        for endpoint_arg_variant in endpoint_arg_variants:
            endpoint_args = sitemap_location.endpoint_args | endpoint_arg_variant
            loc = url_for(route.endpoint, **endpoint_args, _external=True)
            entries.append(
                SitemapEntry(
                    loc=loc,
                    lastmod=lastmod,
                    alternates=alternates,
                    image_locs=image_locs,
                )
            )

    return entries


def _get_sitemap_alternates(
    sitemap_location: SitemapLocation,
    locale_variants: tuple[tuple[dict[str, str], str], ...],
) -> tuple[SitemapAlternate, ...]:
    route = sitemap_location.route
    alternates = [
        SitemapAlternate(
            hreflang,
            url_for(
                route.endpoint,
                **(sitemap_location.endpoint_args | locale_args),
                _external=True,
            ),
        )
        for locale_args, hreflang in locale_variants
    ]
    default_args = sitemap_location.endpoint_args | {"_locale": gen_locale()}
    url = url_for(route.endpoint, **default_args, _external=True)
    alternates.append(SitemapAlternate("x-default", url))
    return tuple(alternates)


def _get_locale_variants() -> tuple[tuple[dict[str, str], str], ...]:
    countries = (country for country in cache.countries if country.in_sitemap)
    languages = (language for language in cache.languages if language.in_sitemap)
    return tuple(
        (
            {"_locale": gen_locale(language.code, country.code)},
            f"{language.code.lower()}-{country.code.upper()}",
        )
        for country, language in itertools.product(countries, languages)
    )


def _get_localized_endpoints() -> set[str]:
    return {
        rule.endpoint
        for rule in current_app.url_map.iter_rules()
        if "_locale" in rule.arguments
    }
