# Stage-04 wiring contract

Six hooks in `scripts/04_build_maps.py` + one in `scripts/<cc>/02d_*.py`.
Line numbers drift — locate each anchor by the grep, then insert the model
block with `cc` (lowercase, e.g. `sk`) and `XX` (uppercase, e.g. `SK`)
substituted. `BG` is the canonical template throughout (numbered-PDF source);
for a source whose merge also carries a commune list, copy `RO` instead (its
augment also merges `geo_communes`).

All examples below assume a standard per-wine spec (grapes + terroir). The
sidecar `source` block written by 02f uses key **`url`** (not `source_url`);
match the BG branch, not the older SI/HR `specifikacija_url` naming.

---

## Hook 1 — `NATIONAL_SPECS_XX` constant

Locate: `grep -n '^EXTRACTED_<CC> = ROOT' scripts/04_build_maps.py`
Insert immediately after that line:

```python
NATIONAL_SPECS_XX = ROOT / "raw" / "xx" / "national-specs-extracted"
```

## Hook 2 — `_XX_NATIONAL_SPEC_BY_SLUG` cache dict

Locate: `grep -n '_BG_NATIONAL_SPEC_BY_SLUG: dict' scripts/04_build_maps.py`
Insert a sibling block after the BG one:

```python
# Slug-keyed cache of XX national-spec provenance, populated by
# augment_xx_records_with_national_specs(). The N grandfathered XX wines
# (only an Ares(...) reference in eAmbrosia, no EU-OJ single document) are
# augmented from the <source_org> per-wine product specification (stage 02f).
_XX_NATIONAL_SPEC_BY_SLUG: dict[str, dict] = {}
```

## Hook 3 — `augment_xx_records_with_national_specs()`

Locate: `grep -n '^def augment_bg_records_with_national_specs' scripts/04_build_maps.py`
Copy that entire function, place it after the last `augment_*` def, rename
`bg`→`cc`, `_BG_`→`_XX_`, `NATIONAL_SPECS_BG`→`NATIONAL_SPECS_XX`,
`"bg"`→`"xx"`, update the docstring + `source_org` default. The merge body
(summary/grapes/geo_area_brief/link_to_terroir/styles/section_roles + the
`stub_reason` `national-spec:` prefix) is identical. If the source carries a
commune list (RO pattern), also merge `record["geo_communes"]`.

## Hook 4 — call site

Locate: `grep -n 'n_aug_bg = augment_bg_records_with_national_specs' scripts/04_build_maps.py`
Insert after that `if n_aug_bg:` block:

```python
    n_aug_xx = augment_xx_records_with_national_specs(extracted_records)
    if n_aug_xx:
        print(
            f"[load] XX national-spec augmentation: {n_aug_xx} stub records enriched",
            file=sys.stderr,
        )
```

## Hook 5 — `_sources_for()` country branch

Locate: `grep -n 'record.get("country") == "bg":' scripts/04_build_maps.py`
Copy the whole BG `if` branch, place it among the `_sources_for` branches,
swap `bg`→`xx`, `_BG_`→`_XX_`. It must surface the `national_spec_*` keys:

```python
    if record.get("country") == "xx":
        xx_spec = record.get("national_spec") or _XX_NATIONAL_SPEC_BY_SLUG.get(
            record.get("slug", ""), {}
        )
        return {
            "country": "xx",
            "eur_lex_url": src.get("final_url") or src.get("source_url") or "",
            "eu_oj_publication_url": src.get("source_url") or "",
            "filename": src.get("filename") or "",
            "fetched_at": src.get("fetched_at") or "",
            "file_number": record.get("file_number") or "",
            "id_eambrosia": record.get("id_eambrosia") or "",
            "national_spec_url": xx_spec.get("url", ""),
            "national_spec_sha256": xx_spec.get("sha256", ""),
            "national_spec_fetched_at": xx_spec.get("fetched_at", ""),
            "national_spec_format": xx_spec.get("format", ""),
            "national_spec_source_org": xx_spec.get("source_org", ""),
            "national_spec_parser_template": xx_spec.get("parser_template", ""),
        }
```

## Hook 6 — `has_augmented_source` gate

Locate: `grep -n 'country == "bg" and slug in _BG_NATIONAL_SPEC_BY_SLUG' scripts/04_build_maps.py`
Add a clause to that `or`-chain:

```python
                or (country == "xx" and slug in _XX_NATIONAL_SPEC_BY_SLUG)
```

This is the silent-failure hook — without it, augmented wines stay flagged
`is_stub=true` and render as bare stubs despite having grapes + terroir.

## Hook 7 — 02d terroir-source fallback (`scripts/<cc>/02d_extract_terroir_facts.py`)

Add the constant near the other path constants:

```python
NATIONAL_SPECS = ROOT / "raw" / "xx" / "national-specs-extracted"
```

Replace `_resolve_lien_and_source` with the BG/GR version: if the on-disk
`link_to_terroir` is shorter than `MIN_LIEN_CHARS`, read the sidecar's
`link_to_terroir` and return `{"pdf_url": ns_src.get("url"), "kind":
"<source_org>-national-spec"}`. Copy `scripts/bg/02d_extract_terroir_facts.py`
`_resolve_lien_and_source` verbatim, swapping the dir + kind.

---

## Wiring-lint — run before the pipeline

Every hook site must reference the country code. zsh-portable (the project
shell is zsh — `${CC^^}` is a bash-ism that errors there), run with `CC=sk`:

```bash
CC=sk; M=scripts/04_build_maps.py; U=$(printf '%s' "$CC" | tr 'a-z' 'A-Z')
echo "1 constant:       $(grep -c "NATIONAL_SPECS_${U} = ROOT" $M)"
echo "2 cache dict:     $(grep -c "_${U}_NATIONAL_SPEC_BY_SLUG: dict" $M)"
echo "3 augment fn:     $(grep -c "^def augment_${CC}_records_with_national_specs" $M)"
echo "4 call site:      $(grep -c "n_aug_${CC} = augment_${CC}_records_with" $M)"
echo "5 _sources_for:   $(grep -c "_${U}_NATIONAL_SPEC_BY_SLUG.get" $M)"
echo "6 augmented gate: $(grep -c "country == \"${CC}\" and slug in _${U}_NATIONAL_SPEC_BY_SLUG" $M)"
echo "7 02d fallback:   $(grep -c 'national-specs-extracted' scripts/${CC}/02d_extract_terroir_facts.py 2>/dev/null || echo 0)"
echo "-- base allowlists (must already be 3; country shipped in 00-03) --"
echo "   in is_wine/src_lang lists: $(grep -E '"es", "pt", "it", "at"' $M | grep -c "\"${CC}\"")"
```

Hooks 1–7 must each print **1**. Note hook 5 greps
`_XX_NATIONAL_SPEC_BY_SLUG.get` (the line that surfaces `national_spec_*`),
**not** the `country == "xx"` string — every country already has a geometry
+ `_sources_for` branch, so a bare-string count is 2 even when the
national-spec provenance was never added. If hook 6 prints 0, that's the
silent-stub bug (augmented wines render as bare stubs) — fix it. The base
allowlist count must be 3 (`is_wine` + two `src_lang` lists); if 0, the
country wasn't wired into stages 00–03 — resolve that first
(see `[[feedback_new_country_is_wine]]`).

## Reference: countries already wired (read one as the live template)

`augment_bg` / `augment_ro` (numbered PDF), `augment_hr` / `augment_si`
(lettered .doc, `specifikacija_url` naming), `augment_gr` (mixed pdf/doc/html),
`augment_cz` (national-tables, no per-wine spec), `augment_it` (MASAF 7z
bundles), `augment_de` (BLE Produktspezifikation), `augment_es` (national
pliego variety augmentation). BG is the cleanest copy target.
