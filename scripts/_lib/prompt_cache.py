"""Prompt caching for the LLM stages (Anthropic only; a no-op elsewhere).

Where the same text is sent more than once, it is placed FIRST in the
system prompt as its own block carrying `cache_control`, so the second
request onwards reads it from the cache at 0.1× the input price instead
of paying for it again:

- stage 02d (20 non-FR scripts): the four sub-section calls of a record
  each resent the whole lien — Barolo's uncapped Art. 9 alone was
  119 K input tokens per record. The lien is now the leading cached
  block; the per-sub-section instructions (which vary) follow it and
  the user turn carries only the sub-section request. FR is left alone:
  it slices section X per sub-section, so its four calls share nothing.
- the gate, the back-check, the LLM audit and the 21 × 02e scripts: the
  system prompt is the same for every record of a batch (per locale for
  02e) — one cached block, read by every request after the first.

A cache prefix must be byte-identical and long enough (Sonnet 5 / 4.6:
1,024 tokens; Opus 5: 512) — a shorter block silently does not cache and
costs nothing extra. The Batch API processes requests concurrently, so
hits are best-effort (Anthropic quotes 30–98 %); the four calls of a
record are submitted adjacently, and the ledger's cache_read /
cache_creation tokens show the achieved rate per batch. The TTL is
`OWM_CACHE_TTL`: "5m" (default — write premium 1.25×, the four-call
pattern breaks even at a 29 % hit rate), "1h" (write 2×, break-even
70 %, for batches whose requests may sit more than 5 minutes apart), or
"off".
"""

from __future__ import annotations

import os

TTL_ENV = "OWM_CACHE_TTL"


def ttl() -> str:
    return (os.environ.get(TTL_ENV) or "5m").strip().lower()


def cache_control() -> dict | None:
    """The `cache_control` value for a cached block, or None when caching is off."""
    t = ttl()
    if t in ("off", "0", "none", "false"):
        return None
    if t == "1h":
        return {"type": "ephemeral", "ttl": "1h"}
    return {"type": "ephemeral"}


def lien_cache_control() -> dict | None:
    """The `cache_control` for a block shared by a record's phased requests
    (a 02d lien): the 1-hour TTL when the batch runner submits one batch
    per phase (`batch.phased()` — the later phases read what the first
    wrote, a read refreshes the timer), else the default TTL — inside one
    concurrent batch the 2× write would be a loss."""
    cc = cache_control()
    if cc is None:
        return None
    if (os.environ.get("OWM_BATCH_PHASED") or "1").strip().lower() not in ("0", "off", "false", "no"):
        return {"type": "ephemeral", "ttl": "1h"}
    return cc


def cached_system(shared: str, rest: str, *, phased: bool = False) -> list[dict] | str:
    """System prompt as [shared block (cached), rest]; plain text when
    caching is off or the shared part is empty. `phased=True` marks the
    block a record shares across phased batch requests (lien_cache_control)."""
    cc = lien_cache_control() if phased else cache_control()
    shared = (shared or "").strip()
    if not shared:
        return rest
    if cc is None:
        return f"{shared}\n\n{rest}"
    return [
        {"type": "text", "text": shared, "cache_control": cc},
        {"type": "text", "text": rest},
    ]


def mark_cached(system: str) -> list[dict] | str:
    """A system prompt shared by every request of a batch, as one cached block."""
    cc = cache_control()
    if cc is None or not system:
        return system
    return [{"type": "text", "text": system, "cache_control": cc}]


def system_text(system) -> str:
    """The plain text of a system prompt, whatever its shape — for
    providers without caching (Mistral, Ollama), the manual round-trip
    files and the batch request hash."""
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))


def split_user_lead(template: str, **fields) -> tuple[str, str]:
    """A "Sub-section: {label}\\n\\nText of …:\\n\\n{lien}" template →
    (the request line, the document block), each formatted."""
    ask, _, doc = template.partition("\n\n")
    return ask.format(**fields), doc.format(**fields)
