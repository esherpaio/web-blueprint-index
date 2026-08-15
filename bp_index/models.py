from dataclasses import dataclass


@dataclass(frozen=True)
class SitemapAlternate:
    hreflang: str
    href: str


@dataclass(frozen=True)
class SitemapEntry:
    loc: str
    lastmod: str
    alternates: tuple[SitemapAlternate, ...] = ()
    image_locs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sitemap:
    loc: str
    lastmod: str
