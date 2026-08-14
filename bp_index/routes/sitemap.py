import itertools
from datetime import datetime

from flask import Response, abort, make_response, render_template
from sqlalchemy import true
from sqlalchemy.orm import joinedload
from web import cdn
from web.app.routing import has_argument
from web.app.urls import url_for
from web.cache import cache
from web.database import conn
from web.database.model import AppRoute, SitemapImageMode, SitemapLocation
from web.locale import gen_locale
from web.setup import config
from web.utils.modifiers import text_to_xml

from bp_index import index_bp
from bp_index.models import Sitemap, SitemapAlternate, SitemapEntry

#
# Routes
#


@index_bp.route("/sitemap.xml")
def sitemap() -> Response:
    group_lastmods: dict[str, datetime] = {}
    for location in _get_sitemap_locations():
        group = location.route.sitemap_group
        group_lastmods[group] = max(
            group_lastmods.get(group, location.lastmod),
            location.lastmod,
        )
    sitemaps: list[Sitemap] = [
        Sitemap(
            loc=url_for("index.sitemap_group", group=group, _external=True),
            lastmod=lastmod.strftime("%Y-%m-%d"),
        )
        for group, lastmod in sorted(group_lastmods.items())
    ]

    image_group_lastmods: dict[str, datetime] = {}
    for location in _get_sitemap_locations(
        image_mode=SitemapImageMode.SEPARATE,
        require_images=True,
    ):
        group = location.route.sitemap_group
        image_group_lastmods[group] = max(
            image_group_lastmods.get(group, location.lastmod),
            location.lastmod,
        )
    sitemaps.extend(
        Sitemap(
            loc=url_for("index.sitemap_group_images", group=group, _external=True),
            lastmod=lastmod.strftime("%Y-%m-%d"),
        )
        for group, lastmod in sorted(image_group_lastmods.items())
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


def _get_sitemap_locations(
    group: str | None = None,
    image_mode: SitemapImageMode | None = None,
    require_images: bool = False,
) -> list[SitemapLocation]:
    with conn.begin() as s:
        query = (
            s.query(SitemapLocation)
            .join(SitemapLocation.route)
            .options(
                joinedload(SitemapLocation.images),
                joinedload(SitemapLocation.route),
            )
            .filter(AppRoute.in_sitemap == true())
        )
        if group is not None:
            query = query.filter(AppRoute.sitemap_group == group)
        if image_mode is not None:
            query = query.filter(AppRoute.sitemap_image_mode == image_mode)
        if require_images:
            query = query.filter(SitemapLocation.images.any())
        sitemap_locations = query.order_by(
            AppRoute.sitemap_group,
            SitemapLocation.route_id,
            SitemapLocation.id,
        ).all()
    return [location for location in sitemap_locations]


def _get_sitemap_entries(
    group: str,
    image_only: bool = False,
) -> list[SitemapEntry]:
    image_mode = SitemapImageMode.SEPARATE if image_only else None
    sitemap_locations = _get_sitemap_locations(
        group,
        image_mode=image_mode,
        require_images=image_only,
    )
    locale_iter_args = (
        [x for x in cache.countries if x.in_sitemap],
        [x for x in cache.languages if x.in_sitemap],
    )

    entries = []
    for sitemap_location in sitemap_locations:
        route = sitemap_location.route
        locale_variants: list[tuple[dict[str, str], str | None]]
        is_localized = has_argument(route.endpoint, "_locale")
        if is_localized:
            locale_variants = [
                (
                    {"_locale": gen_locale(lang.code, country.code)},
                    f"{lang.code.lower()}-{country.code.upper()}",
                )
                for country, lang in itertools.product(*locale_iter_args)
            ]
            if image_only:
                default_locale = f"{config.LOCALE_LANGUAGE_CODE}-{config.LOCALE_COUNTRY_CODE.upper()}"
                locale_variants = [({"_locale": gen_locale()}, (default_locale))]
            if not locale_variants:
                continue
        else:
            locale_variants = [({}, None)]

        alternates = (
            _get_sitemap_alternates(sitemap_location, locale_variants)
            if not image_only and is_localized
            else tuple()
        )
        include_images = (
            image_only or route.sitemap_image_mode == SitemapImageMode.COMBINED
        )
        image_locs = (
            tuple(cdn.url(image.loc) for image in sitemap_location.images)
            if include_images
            else tuple()
        )
        for locale_args_, _ in locale_variants:
            endpoint_args = sitemap_location.endpoint_args | locale_args_
            loc = url_for(route.endpoint, **endpoint_args, _external=True)
            entries.append(
                SitemapEntry(
                    location=sitemap_location,
                    loc=loc,
                    alternates=alternates,
                    image_locs=image_locs,
                )
            )

    return entries


def _get_sitemap_alternates(
    sitemap_location: SitemapLocation,
    locale_variants: list[tuple[dict[str, str], str | None]],
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
        if hreflang is not None
    ]
    default_args = sitemap_location.endpoint_args | {"_locale": gen_locale()}
    alternates.append(
        SitemapAlternate(
            "x-default",
            url_for(route.endpoint, **default_args, _external=True),
        )
    )
    return tuple(alternates)
