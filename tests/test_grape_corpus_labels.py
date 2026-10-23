"""Corpus-wide grape label (scripts/_lib/grape_corpus.py: label_surface / pick_label)."""
from collections import Counter

from _lib.grape_corpus import label_surface, pick_label, spelling_key


def test_label_surface_drops_colour_code_synonym_tail_and_line_break_hyphen():
    assert label_surface("Barbera N.") == "Barbera"
    assert label_surface("Fetească regală B") == "Fetească regală"
    assert label_surface("Αθήρι Β") == "Αθήρι"
    assert label_surface("Durella B. - Durello") == "Durella"
    assert label_surface("Cabernet franc N. - Cabernet") == "Cabernet franc"
    assert label_surface("cabernet- sauvignon") == "cabernet-sauvignon"
    assert label_surface("Folha -de -Figueira") == "Folha-de-Figueira"
    # Spellings stay: a real hyphen, an apostrophe, a breeder number.
    assert label_surface("Cabernet-Sauvignon") == "Cabernet-Sauvignon"
    assert label_surface("Rayon d'Or") == "Rayon d'Or"
    assert label_surface("Optima 113") == "Optima 113"
    assert label_surface("") == ""


def test_spelling_key_folds_case_accents_and_punctuation():
    assert spelling_key("Kékfrankos") == spelling_key("KEKFRANKOS") == "kekfrankos"
    assert spelling_key("Памид") == spelling_key("pamid")
    assert spelling_key("cabernet-sauvignon") == spelling_key("Cabernet Sauvignon")
    assert spelling_key("Côt") != spelling_key("Malbec")


def test_most_frequent_casefold_form_decides_punctuation_and_mixed_case_wins():
    votes = Counter({
        "Cabernet Sauvignon": 236, "cabernet sauvignon": 201, "Cabernet sauvignon": 93,
        "Cabernet-Sauvignon": 62, "CABERNET SAUVIGNON": 60,
    })
    # The 208 FR records whose name is the slug vote for no punctuation.
    assert pick_label("cabernet-sauvignon", votes, slug_votes=208) == "Cabernet Sauvignon"
    assert pick_label("barbera", Counter({"Barbera": 143, "BARBERA": 8, "barbera": 2})) == "Barbera"
    assert pick_label("pinot-blanc", Counter({"pinot blanc": 820, "Pinot blanc": 42})) == "Pinot blanc"


def test_the_slug_spelling_beats_a_more_frequent_synonym():
    assert pick_label("bouvier", Counter({"findling": 23, "Findling": 13, "Bouvier": 6})) == "Bouvier"
    assert pick_label("blauer-wildbacher", Counter({"Wildbacher": 2, "Blauer Wildbacher": 1})) \
        == "Blauer Wildbacher"
    # A DE slug transliterates its umlaut the German way.
    assert pick_label("raeuschling", Counter({"Weißer Räuschling": 9, "Räuschling": 3})) \
        == "Räuschling"


def test_slug_as_name_records_keep_the_slug_when_no_record_spells_it():
    # cot: 190 FR records name it by the slug, the IT ones say Malbech.
    assert pick_label("cot", Counter({"Malbech": 58, "MALBECH": 3}), slug_votes=190) == "cot"
    assert pick_label("cot", Counter({"côt": 1, "Malbech": 58}), slug_votes=190) == "côt"
    assert pick_label("chardonnay", Counter(), slug_votes=1141) == "chardonnay"


def test_fallback_is_the_most_frequent_spelling_accents_kept():
    assert pick_label("blaufrankisch", Counter({
        "kékfrankos": 18, "Frankovka": 12, "Frankovka modrá": 6, "Kekfrankos": 4, "Kékfrankos": 3,
    })) == "Kékfrankos"
    assert pick_label("semillon", Counter({
        "sémillon": 116, "Semillon": 81, "semillon": 71, "Sémillon": 59,
    })) == "Sémillon"
    # A tie between an accented and a stripped form keeps the accents.
    assert pick_label("jubilaeumsrebe", Counter({"Jubiläumsrebe": 4, "Jubilaumsrebe": 4})) \
        == "Jubiläumsrebe"


def test_an_accentless_form_of_the_same_language_is_a_loss_not_a_spelling():
    # The Tejo and Douro cadernos lost their diacritics in pdftotext, and their
    # sub-regiões multiply the vote; the Portuguese spelling with them wins.
    assert pick_label("castelao", Counter({("Castelao", "pt"): 41, ("Castelão", "pt"): 16})) \
        == "Castelão"
    assert pick_label("fernao-pires", Counter({
        ("Fernao Pires", "pt"): 36, ("Fernão-Pires", "pt"): 17, ("Fernão Pires", "pt"): 6,
    })) == "Fernão-Pires"
    # Two languages, two spellings: the count decides.
    assert pick_label("aleatico", Counter({("Aleatico", "it"): 40, ("aléatico", "fr"): 12})) \
        == "Aleatico"
    assert pick_label("malvasia", Counter({
        ("Malvasia", "it"): 60, ("Malvasia", "pt"): 20, ("malvasía", "es"): 30,
    })) == "Malvasia"
    # A Latin transcription beside the Greek spelling is not a loss of the tonos.
    assert pick_label("lagorthi", Counter({("Lagorthi", "gr"): 5, ("Λαγόρθι", "gr"): 3})) \
        == "Lagorthi"


def test_typographic_apostrophes_are_one_form():
    # The FR parser drops the apostrophe; the two Italian apostrophes are one spelling.
    assert pick_label("nero-davola", Counter({
        ("Calabrese", "it"): 54, ("calabrese", "it"): 42, ("nero d avola", "fr"): 12,
        ("Nero d'Avola", "it"): 9, ("Nero d’Avola", "it"): 8, ("Nero D’Avola", "it"): 2,
    })) == "Nero d'Avola"


def test_a_slug_its_records_write_as_itself_never_takes_another_script():
    # ES pliegos name palomino by the slug; the Cypriot capitals are the only
    # other surface of the slug's own spelling.
    assert pick_label("palomino", Counter({("ΠΑΛΟΜΙΝΟ", "el"): 2}), slug_votes=17) == "palomino"
    assert pick_label("palomino", Counter({("ΠΑΛΟΜΙΝΟ", "el"): 2})) == "ΠΑΛΟΜΙΝΟ"


def test_capitals_are_typography_not_spelling():
    # A group seen only in capitals yields to one with a mixed-case spelling …
    assert pick_label("mavro", Counter({"ΝΤΟΠΙΟ ΜΑΥΡΟ": 10, "Μαύρο": 3})) == "Μαύρο"
    assert pick_label("xynisteri", Counter({"ΞΥΝΙΣΤΕΡΙ": 10, "Ξυνιστέρι": 1})) == "Ξυνιστέρι"
    # … a Latin name seen only in capitals is lower-cased for the client's
    # Title Case, a Greek one keeps its capitals (lower case would lose the tonos).
    assert pick_label("bellagna", Counter({"BELLAGNA": 2})) == "bellagna"
    assert pick_label("maratheftiko", Counter({"ΜΑΡΑΘΕΥΤΙΚΟ": 10})) == "ΜΑΡΑΘΕΥΤΙΚΟ"


def test_ties_break_on_the_text_and_an_empty_vote_is_the_slug():
    assert pick_label("x", Counter({"b": 1, "a": 1})) == "a"
    assert pick_label("x", Counter({"b": 1, "a": 1})) == pick_label("x", Counter({"a": 1, "b": 1}))
    assert pick_label("nobody", Counter()) == "nobody"


def test_collect_grape_slugs_reads_a_record_set(monkeypatch, tmp_path):
    import json

    from _lib import grape_corpus

    fr = tmp_path / "fr"
    it = tmp_path / "it"
    fr.mkdir()
    it.mkdir()
    (fr / "b.json").write_text(json.dumps({"grapes": {"details": [
        {"slug": "cabernet-sauvignon", "name": "cabernet- sauvignon"},
        {"slug": "cot", "name": "cot"},
    ]}}), encoding="utf-8")
    (fr / "a.json").write_text(json.dumps({"grapes": {"details": [
        {"slug": "cabernet-sauvignon", "name": "cabernet-sauvignon"},
        {"slug": "cot", "name": "côt"},
    ]}}), encoding="utf-8")
    (it / "_index.json").write_text("{}", encoding="utf-8")
    (it / "c.json").write_text(json.dumps({"grapes": {"details": [
        {"slug": "cabernet-sauvignon", "name": "Cabernet Sauvignon"},
        {"slug": "cabernet-sauvignon", "name": "Cabernet Sauvignon"},
        {"slug": "barbera", "name": "Barbera N."},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(grape_corpus, "_SOURCES", (("fr", fr), ("it", it), ("pt", tmp_path / "nope")))
    corpus = grape_corpus.collect_grape_slugs()
    assert corpus["cabernet-sauvignon"] == {"name": "Cabernet Sauvignon", "by_lang": {"fr": 2, "it": 2}}
    assert corpus["cot"] == {"name": "côt", "by_lang": {"fr": 2}}
    assert corpus["barbera"] == {"name": "Barbera", "by_lang": {"it": 1}}
    assert grape_corpus.per_slug_dominant_lang(corpus)["cabernet-sauvignon"] == "fr"
