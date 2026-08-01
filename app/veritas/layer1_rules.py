"""Deterministic source and language checks for Veritas Shield layer 1."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlsplit

DEFAULT_ALLOWLIST = frozenset(
    {
        "dr.dk",
        "europa.eu",
        "ft.dk",
        "politi.dk",
        "reuters.com",
        "ritzau.dk",
        "who.int",
    }
)

DEFAULT_DENYLIST = frozenset(
    {
        "example-disinformation.invalid",
        "fake-news.invalid",
    }
)

SENSATIONAL_PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    (
        "sensationalist_language",
        re.compile(r"\b(chokerende|skandale|sensation|utroligt)\b", re.IGNORECASE),
        0.10,
    ),
    (
        "urgency_language",
        re.compile(
            r"\b(del nu|før det slettes|de vil ikke have du ved)\b", re.IGNORECASE
        ),
        0.14,
    ),
    (
        "absolute_claim",
        re.compile(
            r"\b(alle ved|ingen tvivl|100\s*% sikkert|beviser endeligt)\b",
            re.IGNORECASE,
        ),
        0.10,
    ),
)


@dataclass(frozen=True)
class Layer1Result:
    score: float
    flags: tuple[str, ...]
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["flags"] = list(self.flags)
        return result


def _normalise_domain(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip().lower()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        hostname = urlsplit(candidate).hostname
        if not hostname:
            return None
        hostname = hostname.encode("idna").decode("ascii").rstrip(".")
        return hostname.removeprefix("www.")
    except (UnicodeError, ValueError):
        return None


def _domain_matches(domain: str, configured: Iterable[str]) -> bool:
    return any(domain == item or domain.endswith(f".{item}") for item in configured)


class Layer1RulesEngine:
    """Score evidence using explicit, auditable rules only.

    The engine deliberately does not make factual truth claims.  It measures
    source reputation, linguistic risk signals, and supplied identity proof.
    """

    def __init__(
        self,
        *,
        allowlist: Iterable[str] = DEFAULT_ALLOWLIST,
        denylist: Iterable[str] = DEFAULT_DENYLIST,
        trusted_authors: Iterable[str] = (),
        trusted_publishers: Iterable[str] = (),
    ) -> None:
        self.allowlist = frozenset(item.lower().strip(".") for item in allowlist)
        self.denylist = frozenset(item.lower().strip(".") for item in denylist)
        self.trusted_authors = frozenset(item.casefold() for item in trusted_authors)
        self.trusted_publishers = frozenset(
            item.casefold() for item in trusted_publishers
        )

    def evaluate(
        self,
        evidence: Mapping[str, Any] | str,
        **overrides: Any,
    ) -> dict[str, Any]:
        data: dict[str, Any]
        if isinstance(evidence, str):
            data = {"text": evidence}
        else:
            data = dict(evidence)
        data.update(overrides)

        text = str(data.get("text") or data.get("content") or "")
        domain = _normalise_domain(data.get("url") or data.get("source_domain"))
        flags: list[str] = []

        if domain is None:
            source_score = 0.40
            flags.append("source_missing")
            source_class = "missing"
        elif _domain_matches(domain, self.denylist):
            source_score = 0.0
            flags.append("source_denylisted")
            source_class = "denylisted"
        elif _domain_matches(domain, self.allowlist):
            source_score = 1.0
            source_class = "allowlisted"
        else:
            source_score = 0.55
            flags.append("source_unverified")
            source_class = "unverified"

        language_score = 1.0
        if not text.strip():
            language_score = 0.35
            flags.append("text_missing")
        else:
            for flag, pattern, penalty in SENSATIONAL_PATTERNS:
                if pattern.search(text):
                    language_score -= penalty
                    flags.append(flag)
            exclamation_count = text.count("!")
            if exclamation_count >= 3:
                language_score -= min(0.18, exclamation_count * 0.02)
                flags.append("excessive_exclamation")
            alpha = [char for char in text if char.isalpha()]
            uppercase_ratio = (
                sum(char.isupper() for char in alpha) / len(alpha) if alpha else 0.0
            )
            if len(alpha) >= 20 and uppercase_ratio > 0.45:
                language_score -= 0.16
                flags.append("excessive_uppercase")
        language_score = max(0.0, min(1.0, language_score))

        author = str(data.get("author") or "").strip()
        publisher = str(data.get("publisher") or "").strip()
        author_verified = bool(data.get("author_verified")) or (
            author.casefold() in self.trusted_authors if author else False
        )
        publisher_verified = bool(data.get("publisher_verified")) or (
            publisher.casefold() in self.trusted_publishers if publisher else False
        )

        identity_parts: list[float] = []
        if author:
            identity_parts.append(1.0 if author_verified else 0.45)
            if not author_verified:
                flags.append("author_unverified")
        else:
            identity_parts.append(0.25)
            flags.append("author_missing")
        if publisher:
            identity_parts.append(1.0 if publisher_verified else 0.50)
            if not publisher_verified:
                flags.append("publisher_unverified")
        else:
            identity_parts.append(0.35)
            flags.append("publisher_missing")
        identity_score = sum(identity_parts) / len(identity_parts)

        score = round(
            max(
                0.0,
                min(
                    1.0,
                    0.45 * source_score + 0.30 * language_score + 0.25 * identity_score,
                ),
            ),
            4,
        )
        return Layer1Result(
            score=score,
            flags=tuple(dict.fromkeys(flags)),
            details={
                "domain": domain,
                "source_class": source_class,
                "source_score": round(source_score, 4),
                "language_score": round(language_score, 4),
                "identity_score": round(identity_score, 4),
                "author_verified": author_verified,
                "publisher_verified": publisher_verified,
            },
        ).to_dict()

    analyze = evaluate
