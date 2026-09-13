from flask import current_app
from sqlalchemy import true
from sqlalchemy.orm import joinedload
from web.app.urls import url_for
from web.database import conn
from web.database.model import AppRoute, SitemapLocation
from web.locale import expects_locale, gen_locale
from web.setup import config

from .models import LlmsLink, LlmsSection


class LlmsService:
    def __init__(self) -> None:
        self._endpoints = self._get_endpoints()

    def get_sections(self) -> list[LlmsSection]:
        links: dict[str, list[LlmsLink]] = {}
        for location in self._get_locations():
            link = self._get_link(location)
            if link is not None:
                links.setdefault(location.route.sitemap_group, []).append(link)
        return [
            LlmsSection(self._get_title(group), tuple(group_links))
            for group, group_links in links.items()
        ]

    @staticmethod
    def get_summary() -> str | None:
        with conn.begin() as session:
            route = (
                session.query(AppRoute).filter_by(endpoint=config.ENDPOINT_HOME).first()
            )
        return route.description if route is not None else None

    def _get_locations(self) -> list[SitemapLocation]:
        with conn.begin() as session:
            return (
                session.query(SitemapLocation)
                .join(SitemapLocation.route)
                .options(joinedload(SitemapLocation.route))
                .filter(
                    AppRoute.in_sitemap == true(),
                    AppRoute.endpoint.in_(self._endpoints),
                )
                .order_by(
                    AppRoute.sitemap_group,
                    SitemapLocation.route_id,
                    SitemapLocation.id,
                )
                .all()
            )

    def _get_link(self, location: SitemapLocation) -> LlmsLink | None:
        route = location.route
        title = location.title or route.breadcrumb_name or route.name
        if not title:
            return None
        endpoint_args = dict(location.endpoint_args)
        # One locale keeps the file small; agents do not need every translation.
        if expects_locale(route.endpoint):
            endpoint_args["_locale"] = gen_locale()
        return LlmsLink(
            title=title,
            url=url_for(route.endpoint, **endpoint_args, _external=True),
            description=location.description or route.description,
        )

    @staticmethod
    def _get_title(group: str) -> str:
        return group.replace("-", " ").replace("_", " ").title()

    @staticmethod
    def _get_endpoints() -> set[str]:
        return {rule.endpoint for rule in current_app.url_map.iter_rules()}
