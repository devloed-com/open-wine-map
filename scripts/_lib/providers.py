"""Shared LLM provider classes for stage 02c / 02d / 02e.

Each provider exposes a `chat(*, system, user, max_tokens, num_ctx)` method
returning the model's text reply (stripped). The providers are
interchangeable behind that interface.

  AnthropicProvider — Anthropic Messages API. Requires ANTHROPIC_API_KEY.
  MistralProvider   — Mistral Chat Completions API. Requires MISTRAL_API_KEY.
  OllamaProvider    — Local Ollama HTTP API.
  ManualProvider    — No-op; used with --emit-todo / --import round-trip.

Each provider exposes a `kind` class attribute used as the `translator_kind`
cache field (`anthropic-api`, `mistral-api`, `ollama`, `manual`).

`max_tokens` and `num_ctx` are accepted by all providers; each takes what
it can use and ignores the rest. AnthropicProvider and MistralProvider use
`max_tokens` only; OllamaProvider uses `num_ctx` (max_tokens is silently
ignored — Ollama's default num_predict is unbounded).
"""

from __future__ import annotations

import os

import requests

from _lib.prompt_cache import system_text

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"

# Per-stage Anthropic defaults — the configuration decided 2026-09-14 after
# the paired experiments in docs/review-terroir-facts-2026-09-12.md:
#   02d extraction  Sonnet 5, thinking off — equal per-bullet reliability to
#                   Sonnet 4.6, 31 % more grounded facts, a third cheaper per
#                   token; the stages' max_tokens were sized for text only.
#   gate            Opus 5 with adaptive thinking — the independent Opus-5
#                   grader caught residuals a Sonnet gate had passed.
#   llm-audit       Opus 5, adaptive (unchanged).
#   02e / back-check stay on Sonnet 4.6 (translation was not re-tested).
# `thinking` is None (send nothing), "disabled" or "adaptive"; the batch
# library and AnthropicProvider both honour it. OWM_BATCH_THINKING overrides.
STAGE_DEFAULTS: dict[str, tuple[str, str | None]] = {
    "02d": ("claude-sonnet-5", "disabled"),
    "gate": ("claude-opus-5", "adaptive"),
    "audit": ("claude-opus-5", "adaptive"),
    "02e": ("claude-sonnet-4-6", None),
    "backcheck": ("claude-sonnet-4-6", None),
    "02c": ("claude-sonnet-4-6", None),
}


_CLAUDE5_PREFIXES = ("claude-sonnet-5", "claude-opus-5", "claude-fable-5", "claude-mythos-5")


def effective_thinking(model: str, thinking: str | None) -> str | None:
    """The thinking mode to send. The Claude 5 family runs adaptive thinking
    when the parameter is omitted (the 4.x models do not), and every stage's
    max_tokens budget is sized for the JSON reply alone — on a stage that
    sets no mode, a Claude 5 model therefore gets "disabled" explicitly
    (2026-09-15: Sonnet 5 on 02e spent the 2,000-token budget on thinking
    and 64 % of the replies came back truncated and were rejected)."""
    if thinking in ("disabled", "adaptive"):
        return thinking
    if any((model or "").startswith(px) for px in _CLAUDE5_PREFIXES):
        return "disabled"
    return None


def stage_default(stage: str | None) -> tuple[str, str | None]:
    """(model id, thinking mode) for an Anthropic stage; the generic default
    for an unknown stage."""
    return STAGE_DEFAULTS.get(stage or "", (DEFAULT_ANTHROPIC_MODEL, None))
DEFAULT_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
DEFAULT_MISTRAL_MODEL = "mistral-medium-latest"
DEFAULT_OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_OLLAMA_MODEL = "mistral-small3.2"
OLLAMA_TIMEOUT_S = 900
MISTRAL_TIMEOUT_S = 300


class AnthropicProvider:
    kind = "anthropic-api"

    def __init__(self, model: str, thinking: str | None = None):
        try:
            import anthropic  # type: ignore
        except ImportError as e:
            raise SystemExit(
                "error: anthropic SDK missing. add it with `uv add anthropic` "
                "(or use --provider=ollama / --provider=manual)."
            ) from e
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise SystemExit("error: ANTHROPIC_API_KEY environment variable is unset.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.thinking = os.environ.get("OWM_BATCH_THINKING") or thinking

    def chat(self, *, system, user: str, max_tokens: int = 1024, **_: object) -> str:
        # `system` is a string or a list of text blocks (prompt_cache.cached_system /
        # mark_cached) — the SDK takes both.
        params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        mode = effective_thinking(self.model, self.thinking)
        if mode:
            params["thinking"] = {"type": mode}
        msg = self.client.messages.create(**params)
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


class MistralProvider:
    kind = "mistral-api"

    def __init__(self, model: str, url: str = DEFAULT_MISTRAL_URL):
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise SystemExit("error: MISTRAL_API_KEY environment variable is unset.")
        self.api_key = api_key
        self.model = model
        self.url = url

    def chat(self, *, system: str, user: str, max_tokens: int = 1024, **_: object) -> str:
        r = requests.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system_text(system)},
                    {"role": "user", "content": user},
                ],
            },
            timeout=MISTRAL_TIMEOUT_S,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()


class OllamaProvider:
    kind = "ollama"

    def __init__(self, model: str, url: str = DEFAULT_OLLAMA_URL):
        self.model = model
        self.url = url

    def chat(self, *, system: str, user: str, num_ctx: int = 4096, **_: object) -> str:
        r = requests.post(
            self.url,
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_text(system)},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_ctx": num_ctx},
            },
            timeout=OLLAMA_TIMEOUT_S,
        )
        r.raise_for_status()
        return r.json()["message"]["content"].strip()


class ManualProvider:
    kind = "manual"

    def chat(self, **_: object) -> str:  # pragma: no cover
        raise RuntimeError(
            "manual provider does not call any model; use --emit-todo PATH "
            "to dump untreated work, fill it in offline, then --import PATH."
        )


def make_provider(
    provider: str,
    *,
    model: str | None,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    mistral_url: str = DEFAULT_MISTRAL_URL,
    stage: str | None = None,
    thinking: str | None = None,
) -> tuple[object | None, str]:
    """Return (provider, translator_id) from CLI args. provider is None for
    manual mode (caller should run the manual-listing path). `stage` picks
    the Anthropic model + thinking default (`STAGE_DEFAULTS`); an explicit
    `model` / `thinking` wins."""
    if provider == "anthropic":
        default_model, default_thinking = stage_default(stage)
        model_id = model or default_model
        return AnthropicProvider(model_id, thinking=thinking or default_thinking), model_id
    if provider == "mistral":
        model_id = model or DEFAULT_MISTRAL_MODEL
        return MistralProvider(model_id, url=mistral_url), model_id
    if provider == "ollama":
        model_id = model or DEFAULT_OLLAMA_MODEL
        return OllamaProvider(model_id, url=ollama_url), model_id
    return None, model or "manual"
