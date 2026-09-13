from dataclasses import dataclass


@dataclass(frozen=True)
class LlmsLink:
    title: str
    url: str
    description: str | None = None


@dataclass(frozen=True)
class LlmsSection:
    title: str
    links: tuple[LlmsLink, ...]
