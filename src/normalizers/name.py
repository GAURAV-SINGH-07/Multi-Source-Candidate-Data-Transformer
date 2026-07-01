"""
Name normalizer — converts raw name strings to proper title case.

Handles real-world edge cases that Python's built-in ``str.title()`` gets
wrong:
    - Hyphenated names:   "anne-marie" → "Anne-Marie"
    - Irish/Scottish:     "o'brien"    → "O'Brien", "mcdonald" → "McDonald"
    - Dutch prefixes:     "van der berg" → "van der Berg" (last word capped)
    - ALL CAPS input:     "PRIYA SHARMA" → "Priya Sharma"
    - Mixed case already correct: preserved without change

The factor is 1.0 if the input was already proper-cased (no change needed)
or 0.90 if we had to normalize it — slight penalty because any rule-based
casing algorithm can mishandle unusual names.
"""

import re
from .result import NormalizationResult

# Dutch/German/French lowercase particles that stay lowercase unless last
_PARTICLES = frozenset({
    "van", "de", "der", "den", "di", "da", "du", "des",
    "von", "zu", "la", "le", "les", "del",
})

# Prefixes that get special casing (Mc → McX, Mac → MacX)
_MC_RE = re.compile(r"\bMc([a-z])", re.IGNORECASE)
_MAC_RE = re.compile(r"\bMac([a-z])", re.IGNORECASE)


def normalize_name(raw: str) -> NormalizationResult:
    """Normalize *raw* name to proper title case.

    Args:
        raw: Raw name string in any case.

    Returns:
        :class:`NormalizationResult` with a title-cased name.
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            value=None,
            success=False,
            factor=0.0,
            method="empty_input",
            original=raw,
            warning="Empty name string",
        )

    stripped = raw.strip()
    normalized = _apply_title_case(stripped)
    changed = normalized != stripped

    return NormalizationResult(
        value=normalized,
        success=True,
        factor=0.90 if changed else 1.0,
        method="normalized_case" if changed else "already_proper_case",
        original=raw,
        warning=None,
    )


def _apply_title_case(name: str) -> str:
    """Apply intelligent title-casing to *name*."""
    # Split on spaces and hyphens, normalizing each token independently
    parts = re.split(r"(\s+|-)", name)
    result_parts: list[str] = []

    tokens = [p for p in parts if p and not re.match(r"^[\s-]+$", p)]
    separators = [p for p in parts if re.match(r"^[\s-]+$", p)]

    # Interleave tokens and separators
    processed_tokens = _process_tokens(tokens)

    # Rebuild with original separators
    sep_iter = iter(separators)
    token_iter = iter(processed_tokens)
    output: list[str] = []
    for i, part in enumerate(parts):
        if re.match(r"^[\s-]+$", part):
            output.append(part)
        else:
            output.append(next(token_iter, part))

    return "".join(output)


def _process_tokens(tokens: list[str]) -> list[str]:
    """Title-case a list of name tokens, applying special rules."""
    result: list[str] = []
    for i, token in enumerate(tokens):
        lower = token.lower()
        is_last = (i == len(tokens) - 1)

        # Particles stay lowercase unless they're the last token
        if lower in _PARTICLES and not is_last:
            result.append(lower)
            continue

        # O'Brien, O'Connor
        if re.match(r"^o'[a-z]", lower):
            result.append("O'" + lower[2:].capitalize())
            continue

        # McDonald, MacDonald
        mc_match = _MC_RE.match(token)
        if mc_match:
            result.append("Mc" + mc_match.group(1).upper() + token[3:].lower())
            continue

        mac_match = _MAC_RE.match(token)
        if mac_match:
            result.append("Mac" + mac_match.group(1).upper() + token[4:].lower())
            continue

        result.append(token.capitalize())
    return result
