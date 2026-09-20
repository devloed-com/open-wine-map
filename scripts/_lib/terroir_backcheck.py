"""The translation back-check over stage-02e caches (review 2026-09-12,
R6): per (record, target locale) one model request compares every
translated bullet with its source-language bullet and returns a
corrected translation where the rendering changed the meaning — a
number or unit slip (250–290 m → 250–490 m), a dropped, added or
upgraded hedge ("weakly" → "moderately"), a name back-formed from an
adjective ("the Caiata area" from *caiatino*), a false friend or calque
from the watch-list (*generoso* → "generous", *tirage* → "disgorgement",
Burgundian *climat* → "climate", *Lehm* → "clay", *Pintes* → "Pinot"), a
common noun left in the source language, a place name that has an
established exonym. Fixes are applied deterministically (`apply_fixes`)
under the same guards as the gate's rewrites — no number that is in
neither the source bullet nor the current translation, no arrow, sane
length — and every checked bullet carries `check` ({verdict, issue[,
original]}).

Pure functions here; I/O, batch and cache writing live in
`scripts/02e_verify_terroir_facts.py`.
"""

from __future__ import annotations

import json
import re

from _lib import llm_json
from _lib.exonyms import exonym_hits
from _lib.terroir_dedupe import _numbers
from _lib.terroir_feedback import _clip, _safe
from _lib.terroir_normalize import normalize_bullet

BACKCHECK_VERSION = "backcheck-v2"
FIX_MAX_CHARS = 360

_LANG_NAME = {
    "en": "English", "fr": "French", "es": "Spanish", "nl": "Dutch", "de": "German", "it": "Italian",
    "pt": "Portuguese", "el": "Greek", "bg": "Bulgarian", "hu": "Hungarian", "cs": "Czech", "sk": "Slovak",
    "sl": "Slovenian", "hr": "Croatian", "ro": "Romanian",
}

WATCH_LIST = (
    "climat (Burgundian named site — keep 'climat', never 'climate')",
    "tirage (the bottling for the second fermentation — never 'disgorgement', which is dégorgement)",
    "generoso / vino generoso (a fortified wine — never 'generous')",
    "Lehm (loam — not clay, which is Ton)",
    "Spritzigkeit / spritzig (a light sparkle — not 'spiciness')",
    "capa (Spanish: depth of colour — 'capa alta' is deep colour, never 'layer')",
    "tipologia (a wine type / style, never 'typology')",
    "Urgestein (crystalline basement / primary rock, never 'primeval rock')",
    "Pintes (a Hungarian grape variety, never 'Pinot')",
    "Немски / Рейнски ризлинг (Riesling) versus Италиански ризлинг (Welschriesling) — never swap them",
    "Rodopi / Родопи → Rhodopes (EN, FR) / Rhodopen (NL) / Ródope (ES); Stara Planina stays 'Stara Planina' (a one-time gloss '(Balkan Mountains)' is fine); Bayern → Bavaria / Baviera / Bavière / Beieren",
    "a river valley in Dutch is 'de X-vallei' or 'het X-dal' (Marnevallei, het Marnedal) — a blend such as 'Marnedallei' or 'Audedallei' is not a word and must be fixed",
)

SYSTEM = """You are the back-checker for Open Wine Map's machine-translated terroir facts. Each record's bullets were extracted in the source language from a wine regulator's specification and then translated into the target language. You receive both versions side by side; the SOURCE bullet is authoritative. Your job is to find every place where the translation changed the meaning, and to give the corrected translation.

Flag a bullet ("fix") when the translation:
- changes, drops or adds a number, a unit, a date, a range bound, a direction (north/south, above/below), a comparative;
- drops, adds or upgrades a hedge or a quantifier ("mainly" → nothing; "weakly" → "moderately"; "often" → "always"; "some" → "all");
- names the wrong entity: a grape, place, formation, wind, institution or person rendered as a different one, a name back-formed from an adjective ("the Caiata area" for caiatino, which means "of Caiazzo"), an appellation name translated instead of kept;
- uses a false friend or calque from this watch-list, or otherwise gives a wine term a wrong sense: {watch_list};
- leaves a common noun (a generic soil, rock, climate, harvest or wine-law term) untranslated in the source language, or keeps a source-form geographic name that has an established target-language exonym (named formations, named winds, appellation names and grape names stay verbatim — those are correct);
- garbles grammar so the sentence no longer says what the source says.
Do NOT flag: a legitimate simplification; a different but equivalent number format; a synonym in register; a sentence that is merely awkward but faithful. When in doubt, "ok".

For a "fix", give "fix": the full corrected bullet in the target language, faithful to the SOURCE bullet, one complete sentence ending with a period, without adding content. Keep the source's proper nouns exactly; transliterate Greek and Cyrillic to the EU-official Latin form. A "fix" verdict MUST carry a non-empty "fix" — if you cannot write the corrected sentence, answer "ok" and put your concern in "issue".

Answer ONLY with JSON, no text before or after:
{"facts": [{"i": 0, "verdict": "ok|fix", "issue": "short reason, or empty", "fix": ""}, ...]}
One object per bullet, in order, with "i" equal to the bullet's index."""


def system_prompt() -> str:
    return SYSTEM.replace("{watch_list}", "; ".join(WATCH_LIST))


def _constraints_block(fb: dict | None) -> str:
    if not fb:
        return ""
    lines: list[str] = []
    for c in fb.get("do_not_claim") or []:
        if (c.get("stage") or "extraction") not in ("translation", "both"):
            continue
        claim = _clip(c.get("claim_en") or c.get("claim_src") or "", 220)
        why = _clip(c.get("why") or "", 240)
        if claim:
            lines.append(f"- A previous review verified this rendering as misleading: «{claim}» — {why}")
    return ("PRIOR-REVIEW NOTES FOR THIS RECORD\n" + "\n".join(lines) + "\n\n") if lines else ""


def build_user_message(
    *, name: str, source_lang: str, target_lang: str, source_facts: list[dict],
    translated: list[dict], feedback: dict | None, gi_forms: frozenset[str] = frozenset(),
) -> str:
    src_name = _LANG_NAME.get(source_lang, source_lang)
    tgt_name = _LANG_NAME.get(target_lang, target_lang)
    lines = []
    for i, (sf, tf) in enumerate(zip(source_facts, translated)):
        hits = exonym_hits(tf.get("bullet") or "", target_lang, gi_forms=gi_forms)
        flag = f"\nDETECTOR: source-form place name(s) still present: {', '.join(hits)}" if hits else ""
        lines.append(
            f"#{i} [{sf.get('subsection') or ''}]\n"
            f"SOURCE ({src_name}): {sf.get('bullet') or ''}\n"
            f"TRANSLATION ({tgt_name}): {tf.get('bullet') or ''}{flag}"
        )
    return _safe(
        f"RECORD: {name} — {src_name} → {tgt_name}; {len(translated)} bullets.\n\n"
        f"{_constraints_block(feedback)}"
        "BULLETS\n" + "\n\n".join(lines)
    )


# ─────────────────────────────────────────────────────────── parsing ──

_ROW_SPLIT_RE = re.compile(r"\}\s*,\s*\{")
_I_RE = re.compile(r'"i"\s*:\s*(\d+)')
_VERDICT_RE = re.compile(r'"verdict"\s*:\s*"([A-Za-z]+)"')
_ISSUE_RE = re.compile(r'"issue"\s*:\s*"(.*?)"\s*,\s*"fix"', re.S)
_FIX_RE = re.compile(r'"fix"\s*:\s*"(.*?)"\s*(?:,\s*"|\}|$)', re.S)


def _recover_rows(s: str) -> list[dict]:
    start = s.find('"facts"')
    body = s[start:] if start >= 0 else s
    rows: list[dict] = []
    for chunk in _ROW_SPLIT_RE.split(body):
        m_i, m_v = _I_RE.search(chunk), _VERDICT_RE.search(chunk)
        if not (m_i and m_v):
            continue
        m_is, m_f = _ISSUE_RE.search(chunk), _FIX_RE.search(chunk)
        rows.append({
            "i": int(m_i.group(1)), "verdict": m_v.group(1),
            "issue": m_is.group(1).replace('\\"', '"') if m_is else "",
            "fix": m_f.group(1).replace('\\"', '"') if m_f else "",
        })
    return rows


def parse_checks(raw: str, n: int) -> tuple[list[dict] | None, str | None]:
    """A list aligned on bullet index ({verdict, issue, fix}); a bullet the
    reply omits is `ok`. (None, error) for a reply with no gradable rows."""
    s = llm_json.strip_fences(raw or "")
    rows = None
    try:
        data = json.loads(s)
        rows = data.get("facts") if isinstance(data, dict) else None
    except ValueError:
        m = re.search(r"\{.*\}", s, re.S)
        if not m:
            return None, "no JSON object in reply"
        try:
            data = json.loads(m.group(0))
            rows = data.get("facts") if isinstance(data, dict) else None
        except ValueError:
            rows = _recover_rows(m.group(0)) or None
            if rows is None:
                return None, "unparseable JSON and no recoverable rows"
    if not isinstance(rows, list):
        return None, "no `facts` list"
    out = [{"verdict": "ok", "issue": "", "fix": ""} for _ in range(n)]
    seen = 0
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            i = int(r.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < n:
            continue
        verdict = str(r.get("verdict") or "ok").strip().lower()
        out[i] = {
            "verdict": "fix" if verdict == "fix" else "ok",
            "issue": " ".join(str(r.get("issue") or "").split())[:300],
            "fix": " ".join(str(r.get("fix") or "").split()),
        }
        seen += 1
    if seen == 0 and n:
        return None, "reply graded none of the bullets"
    return out, None


# ──────────────────────────────────────────────────────── application ──


def fix_ok(source_bullet: str, current: str, fix: str) -> str | None:
    fx = (fix or "").strip()
    if not fx:
        return "empty"
    if fx == (current or "").strip():
        return "unchanged"
    if "→" in fx:
        return "arrow"
    if len(fx) > FIX_MAX_CHARS or len(fx) < 15:
        return "length"
    new_nums = _numbers(fx) - _numbers(source_bullet) - _numbers(current)
    if new_nums:
        return f"new numbers {sorted(new_nums)}"
    return None


def apply_fixes(
    translated: list[dict], source_facts: list[dict], checks: list[dict], *, lang: str, run: str, model: str,
) -> dict:
    """Apply the back-check to a translation cache's facts (in place on
    copies). Returns {facts, fixed: [{index, from, to, issue}], rejected:
    [{index, reason}], missing_fixes: [{index, issue}]}."""
    out: list[dict] = []
    fixed: list[dict] = []
    rejected: list[dict] = []
    missing: list[dict] = []
    for i, (tf, sf, c) in enumerate(zip(translated, source_facts, checks)):
        new = dict(tf)
        check = {"verdict": c["verdict"], "issue": c.get("issue") or "", "version": BACKCHECK_VERSION,
                 "run": run, "model": model}
        if c["verdict"] == "fix":
            reason = fix_ok(sf.get("bullet") or "", tf.get("bullet") or "", c.get("fix") or "")
            if reason == "empty":
                # The model flagged a concern it could not phrase (512 did in
                # r1): keep the translation, keep the issue, list the case.
                check["verdict"] = "ok"
                check["fix_missing"] = True
                missing.append({"index": i, "issue": check["issue"]})
            elif reason is None:
                fx = normalize_bullet(c["fix"], lang)
                check["original"] = tf.get("bullet") or ""
                new["bullet"] = fx
                fixed.append({"index": i, "from": tf.get("bullet") or "", "to": fx, "issue": check["issue"]})
            else:
                check["verdict"] = "fix-rejected"
                check["rejected_reason"] = reason
                check["proposed_fix"] = c.get("fix") or ""
                rejected.append({"index": i, "reason": reason})
        new["check"] = check
        out.append(new)
    return {"facts": out, "fixed": fixed, "rejected": rejected, "missing_fixes": missing}
