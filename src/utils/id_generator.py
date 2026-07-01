"""
Candidate ID generation.

IDs are deterministic when a primary email is available (UUID5 in the
DNS namespace). This means the same candidate will always receive the
same ID regardless of which run produced their profile — useful for
deduplication in downstream systems.

When no email is available, we fall back to a random UUID4 and emit a
warning, since idempotency is then not guaranteed.
"""

import uuid
import logging

log = logging.getLogger(__name__)

# Stable namespace for candidate UUID5 generation
_CANDIDATE_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_candidate_id(primary_email: str | None) -> str:
    """Generate a stable candidate ID.

    If *primary_email* is provided, returns a deterministic UUID5 derived
    from the email address. The same email will always produce the same ID.

    If *primary_email* is ``None``, falls back to a random UUID4 and logs
    a warning.

    Args:
        primary_email: The candidate's primary (first) email address,
                       already normalized to lowercase.

    Returns:
        A UUID string (without braces).
    """
    if primary_email:
        return str(uuid.uuid5(_CANDIDATE_NAMESPACE, primary_email.lower().strip()))

    log.warning(
        "No primary email available — generating random candidate ID. "
        "This ID will not be idempotent across runs."
    )
    return str(uuid.uuid4())
