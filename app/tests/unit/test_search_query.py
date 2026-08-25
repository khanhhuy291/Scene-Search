"""Query understanding and negation-aware caption matching.

The cases that matter most here are the ones where the naive implementation looks
fine and is wrong: a caption that mentions pedestrians while asserting there are
none, and a negation that must not leak across a clause boundary into the rest of
a 700-character description.
"""

from __future__ import annotations

import pytest

from search.query import (
    caption_polarity,
    concept_names,
    evaluate_caption,
    parse_query,
    resolve_concept,
    split_clauses,
)

# -- polarity ----------------------------------------------------------------


def test_plain_mention_is_present() -> None:
    assert caption_polarity("Several pedestrians cross the road.", "people") == "present"


def test_never_mentioned_is_unknown() -> None:
    # Unknown is not absent. Captions summarise rather than inventory, so silence
    # is not evidence either way, and collapsing the two would make "without
    # people" reject every frame whose caption simply did not comment.
    assert caption_polarity("A wet road at night.", "people") == "unknown"


@pytest.mark.parametrize(
    "caption",
    [
        "The road is quiet, with no visible pedestrians.",
        "There are no pedestrians in sight.",
        "The street is devoid of people.",
        "No one is walking along the pavement.",
        "The pavement is empty of pedestrians.",
        "Pedestrians are not visible in this frame.",
    ],
)
def test_negated_mention_is_absent(caption: str) -> None:
    """The case a keyword veto gets backwards.

    Every one of these captions contains a people word while stating the
    opposite. Matching on the word alone would reject exactly the frames a
    "without people" query is looking for.
    """

    assert caption_polarity(caption, "people") == "absent"


def test_negation_does_not_cross_a_clause_boundary() -> None:
    # The "no" belongs to the traffic lights. Letting it run to the end of the
    # caption would mark the pedestrians absent when they are the subject of the
    # next clause.
    caption = "There are no traffic lights here, but several pedestrians are crossing."
    assert caption_polarity(caption, "traffic_light") == "absent"
    assert caption_polarity(caption, "people") == "present"


def test_negation_does_not_reach_backwards() -> None:
    caption = "Cars are parked along the kerb and no people are around."
    assert caption_polarity(caption, "car") == "present"
    assert caption_polarity(caption, "people") == "absent"


def test_negation_carries_across_a_coordinated_list() -> None:
    caption = "The scene is static, with no visible pedestrians or cyclists."
    assert caption_polarity(caption, "people") == "absent"
    assert caption_polarity(caption, "cyclist") == "absent"


def test_one_unnegated_mention_outweighs_a_negated_one() -> None:
    # Presence is positive evidence; a later denial elsewhere in a long caption
    # does not undo having seen them.
    caption = "Two pedestrians wait at the kerb. There are no other people nearby."
    assert caption_polarity(caption, "people") == "present"


def test_mention_count_is_evidence_strength() -> None:
    sparse = split_clauses("A car drives past a snow bank.")
    dense = split_clauses("Snow covers the road. Snow is falling and snow lines the kerb.")
    assert resolve_concept(sparse, "snow") == ("present", 1)
    polarity, mentions = resolve_concept(dense, "snow")
    assert polarity == "present"
    assert mentions > 1


def test_unknown_concept_falls_back_to_its_literal_form() -> None:
    assert caption_polarity("A yellow school bus stops ahead.", "school bus") == "present"
    assert caption_polarity("There is no school bus.", "school bus") == "absent"


# -- query parsing -----------------------------------------------------------


def test_exclusion_is_removed_from_the_embedded_text() -> None:
    """The exclusion must not reach the encoder.

    Contrastive text encoders have no representation for negation, so embedding
    "rainy day without people" lands *closer* to frames containing people than
    "rainy day" alone does. The exclusion is enforced structurally instead.
    """

    parsed = parse_query("rainy day without people")
    assert parsed.semantic_text == "rainy day"
    assert parsed.required == ("rain",)
    assert parsed.excluded == ("people",)


@pytest.mark.parametrize(
    "query",
    [
        "night driving with no pedestrians",
        "night driving without people",
        "night driving, excluding pedestrians",
    ],
)
def test_negation_markers_are_equivalent(query: str) -> None:
    parsed = parse_query(query)
    assert parsed.excluded == ("people",)
    assert "pedestrian" not in parsed.semantic_text.lower()


def test_vietnamese_query_resolves_to_the_same_constraints() -> None:
    english = parse_query("rainy day without pedestrians")
    vietnamese = parse_query("trời mưa, không có người đi bộ")
    assert vietnamese.required == english.required == ("rain",)
    assert vietnamese.excluded == english.excluded == ("people",)
    assert vietnamese.unmatched_exclusions == ()


def test_vietnamese_query_embeds_english_concept_glosses() -> None:
    parsed = parse_query("trời mưa, có người đi bộ băng qua trước xe")
    assert "rain" in parsed.required
    assert "people" in parsed.required
    assert "rain" in parsed.embedding_text.lower()
    assert "pedestrian" in parsed.embedding_text.lower()
    assert parse_query("rainy day with pedestrians").embedding_text == "rainy day with pedestrians"


def test_removing_a_required_chip_drops_it_from_the_embedding() -> None:
    from dataclasses import replace

    parsed = parse_query("rainy day without people")
    assert "rain" in parsed.embedding_text.lower()
    widened = replace(parsed, required=())
    assert "rain" not in widened.embedding_text.lower()


def test_dangling_connective_is_trimmed_from_the_embedded_text() -> None:
    assert parse_query("night driving with no pedestrians").semantic_text == "night driving"


def test_emptiness_word_implies_excluding_people() -> None:
    parsed = parse_query("empty residential street")
    assert "people" in parsed.excluded
    assert parsed.required == ("residential",)


def test_unknown_exclusion_is_reported_rather_than_silently_dropped() -> None:
    parsed = parse_query("a highway without hot air balloons")
    assert parsed.excluded == ()
    assert parsed.unmatched_exclusions == ("hot air balloons",)


def test_query_of_only_an_exclusion_still_has_something_to_embed() -> None:
    parsed = parse_query("without people")
    assert parsed.semantic_text
    assert parsed.excluded == ("people",)


def test_empty_query_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_query("   ")


def test_multiple_exclusions_accumulate() -> None:
    parsed = parse_query("a highway without trucks and without buses")
    assert set(parsed.excluded) == {"truck", "bus"}


# -- verdicts ----------------------------------------------------------------


def test_excluded_concept_present_rejects_the_keyframe() -> None:
    parsed = parse_query("rainy day without people")
    caption = "A rainy street with several pedestrians crossing."
    assert evaluate_caption(caption, parsed).admissible is False


def test_excluded_concept_explicitly_absent_is_admitted_and_recorded() -> None:
    parsed = parse_query("rainy day without people")
    verdict = evaluate_caption("A rainy street with no visible pedestrians.", parsed)
    assert verdict.admissible is True
    assert verdict.denied == ("people",)
    assert verdict.confirmed == ("rain",)


def test_excluded_concept_unmentioned_is_admitted_without_a_denial() -> None:
    parsed = parse_query("rainy day without people")
    verdict = evaluate_caption("Rain streaks the windshield on a quiet road.", parsed)
    assert verdict.admissible is True
    assert verdict.denied == ()


def test_required_concept_explicitly_absent_rejects_the_keyframe() -> None:
    """A caption saying "no snow" is not a snowy scene, whatever its vector says.

    This is the guard against the ANN stage carrying in a visually similar frame
    whose description contradicts the query.
    """

    parsed = parse_query("snowy day")
    assert evaluate_caption("A cold winter road with no snow on it.", parsed).admissible is False


def test_lexicon_covers_the_concepts_the_corpus_is_searched_on() -> None:
    names = set(concept_names())
    assert {"people", "rain", "snow", "night", "fog", "highway", "tunnel"} <= names
