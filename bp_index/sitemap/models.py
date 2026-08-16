from dataclasses import dataclass
from enum import StrEnum


class SitemapKind(StrEnum):
    PAGES = "pages"
    IMAGES = "images"


@dataclass(frozen=True)
class SitemapIndexEntry:
    loc: str


@dataclass(frozen=True)
class SitemapAlternate:
    hreflang: str
    href: str


@dataclass(frozen=True)
class SitemapUrl:
    loc: str
    lastmod: str
    alternates: tuple[SitemapAlternate, ...] = ()
    image_locs: tuple[str, ...] = ()

    @property
    def reference_count(self) -> int:
        return 1 + len(self.alternates) + len(self.image_locs)


@dataclass(frozen=True)
class SitemapLocationBundle:
    urls: tuple[SitemapUrl, ...]


@dataclass(frozen=True)
class RenderedSitemapBundle:
    xml: bytes
    url_count: int


@dataclass(frozen=True)
class SitemapEnvelope:
    prefix: bytes
    suffix: bytes

    @property
    def byte_count(self) -> int:
        return len(self.prefix) + len(self.suffix)


@dataclass(frozen=True)
class SitemapPart:
    fragments: tuple[bytes, ...]
    url_count: int
    byte_count: int


@dataclass(frozen=True)
class SitemapLimits:
    target_urls: int = 40_000
    target_bytes: int = 40 * 1024 * 1024
    max_urls: int = 50_000
    max_bytes: int = 50 * 1024 * 1024
