"""Tolerant parsing of LLM extraction / translation JSON replies.

LLMs reliably emit *almost*-JSON: the structure is sound, but verbatim
text copied into a string value often carries unescaped double-quotes
(a cahier citing « une grande "montille" »), and strict ``json.loads``
rejects the whole reply. Each parser here tries strict JSON first, then
falls back to a structure-anchored recovery that locates string values
by their surrounding JSON delimiters rather than by quote-balancing — so
stray quotes inside a value no longer break the parse.

Used by stage 02d (`parse_facts`) and stage 02e (`parse_str_array`),
every country.
"""

from __future__ import annotations

import json
import re


def strip_fences(raw: str) -> str:
    """Drop a leading ```json fence and trailing ``` if present."""
    s = (raw or "").strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.rsplit("```", 1)[0]
    return s.strip()


def _decode_value(v: str) -> str:
    """Turn a raw JSON-string body (which may contain unescaped ") into the
    actual string: escape stray quotes, then JSON-decode so real escape
    sequences (\\n, \\", …) are interpreted."""
    body = re.sub(r'(?<!\\)"', r'\\"', v)
    try:
        return json.loads(f'"{body}"')
    except Exception:  # noqa: BLE001
        return v.replace('\\"', '"')


# One fact object: keys in the order the 02d prompt dictates. Each value is
# captured non-greedily up to the *next key delimiter*, so unescaped quotes
# inside the value are absorbed rather than ending the match early.
_FACT_RE = re.compile(
    r'"bullet"\s*:\s*"(?P<bullet>.*?)"\s*,\s*'
    r'"cahier_quote"\s*:\s*"(?P<cahier>.*?)"\s*,\s*'
    r'"wiki_quote"\s*:\s*"(?P<wiki>.*?)"\s*\}',
    re.S,
)


def parse_facts(raw: str) -> tuple[dict | None, str | None]:
    """Parse a stage-02d extraction reply into ({"facts": [...]}, None), or
    (None, error). Recovers from unescaped quotes in bullet/quote values."""
    cleaned = strip_fences(raw)
    m = re.search(r"\{.*\}", cleaned, re.S)
    if m:
        cleaned = m.group()
    strict_err = "no JSON object found"
    try:
        obj = json.loads(cleaned)
    except Exception as e:  # noqa: BLE001
        strict_err = str(e)
    else:
        if isinstance(obj, dict):
            return obj, None
        strict_err = "top-level JSON value is not an object"
    # recovery — anchor each fact triple on its key labels
    facts = [
        {
            "bullet": _decode_value(fm["bullet"]),
            "cahier_quote": _decode_value(fm["cahier"]),
            "wiki_quote": _decode_value(fm["wiki"]),
        }
        for fm in _FACT_RE.finditer(cleaned)
    ]
    if facts:
        return {"facts": facts}, None
    if re.search(r'"facts"\s*:\s*\[\s*\]', cleaned):
        return {"facts": []}, None
    return None, f"unrepairable JSON: {strict_err}"


def parse_str_array(raw: str, expected_len: int) -> tuple[list[str] | None, str | None]:
    """Parse a stage-02e translation reply (a JSON array of `expected_len`
    strings) into (list, None) or (None, error). Recovers from unescaped
    quotes by marking the structural quotes, escaping the rest, re-parsing."""
    cleaned = strip_fences(raw)
    start = cleaned.find("[")
    if start < 0:
        return None, "no array found"
    body = cleaned[start:]
    try:
        arr, _ = json.JSONDecoder().raw_decode(body)
        if isinstance(arr, list) and len(arr) == expected_len:
            return [str(x).strip() for x in arr], None
    except Exception:  # noqa: BLE001
        pass
    end = body.rfind("]")
    if end < 0:
        return None, "no array close"
    seg = body[: end + 1]
    open_m, sep_m, close_m = "\x00", "\x01", "\x02"
    seg = re.sub(r'\[\s*"', "[" + open_m, seg, count=1)
    seg = re.sub(r'"\s*\]$', close_m + "]", seg, count=1)
    seg = re.sub(r'"\s*,\s*"', sep_m, seg)
    seg = seg.replace('\\"', '"').replace('"', '\\"')
    seg = seg.replace(open_m, '"').replace(close_m, '"').replace(sep_m, '", "')
    try:
        arr = json.loads(seg)
    except Exception as e:  # noqa: BLE001
        return None, f"unrepairable array: {e}"
    if not isinstance(arr, list):
        return None, "recovered value is not an array"
    if len(arr) != expected_len:
        return None, f"length mismatch: got {len(arr)}, expected {expected_len}"
    return [str(x).strip() for x in arr], None
