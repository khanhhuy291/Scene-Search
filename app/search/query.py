"""Query understanding and caption evidence for scene search.

Two problems are solved here, and both are the difference between a search that
looks plausible and one that is correct.

**Negation belongs to the keyframe, not the video.** "A rainy day without
people" is satisfied by a keyframe with rain and no people in it, even when the
same video shows a pedestrian eight seconds later. Every judgement below is made
per keyframe for that reason; grouping to one result per video happens after
filtering, never before.

**A caption that mentions a thing may be asserting its absence.** The corpus
captions are written by a vision-language model and habitually say things like
*"The road is relatively quiet, with no visible pedestrians."* A keyword veto on
``pedestrian`` would discard precisely the frames a "without people" query is
asking for -- the ones where absence was explicitly observed. So a caption is not
matched with a substring test but resolved to a three-valued
:data:`Polarity`: the concept is ``present``, explicitly ``absent``, or
``unknown`` because the caption never mentions it.

The negation scoping follows the NegEx approach: a negation cue applies forward
until a scope terminator (a clause boundary, or a contrast word like "but").
That is an approximation -- it will mislabel a caption that negates across a
comma -- but it is a documented and testable one, and it is dramatically better
than ignoring negation, which is wrong on thousands of frames in this corpus.

Nothing here calls an LLM. Query parsing that depends on a network round trip
cannot be unit tested, adds latency to the one path with a latency budget, and
fails in a way that looks like a relevance bug.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Polarity = Literal["present", "absent", "unknown"]

# Surface forms, per canonical concept, as they appear in captions *and* as users
# type them -- one lexicon serves both directions, so "pedestrians" in a query
# and "pedestrian" in a caption resolve to the same concept.
#
# Vietnamese forms are query-side only. The corpus captions are English, so a
# Vietnamese pattern can never match one; it exists so that "không có người đi
# bộ" resolves to the same exclusion that "without pedestrians" does, which the
# MVP requires (definition of done, step 2: the query is accepted in Vietnamese
# without transliteration).
#
# Deliberately narrow. A concept earns a place here when it is both common in
# this corpus (verified against caption frequencies) and something an engineer
# would plausibly filter a training set on. Anything absent from this table still
# works through the semantic path and through the literal fallback in
# :func:`concepts_in_phrase`; it just does not get exhaustive lexical recall.
_CONCEPT_PATTERNS: dict[str, tuple[str, ...]] = {
    # Actors
    "people": (
        r"pedestrians?",
        r"people",
        r"persons?",
        r"crowds?",
        r"humans?",
        r"men",
        r"women",
        r"man",
        r"woman",
        r"joggers?",
        r"walkers?",
        r"passers-?by",
        r"bystanders?",
        # Indefinite pronouns are people words too. "No one is walking" states an
        # absence of people, and it does so without ever using a people noun, so
        # without these the sentence reads as no comment at all.
        r"no ?one",
        r"nobody",
        r"anyone",
        r"someone",
        r"anybody",
        r"somebody",
        r"souls?",
        r"người đi bộ",
        r"khách bộ hành",
        r"đám đông",
        r"người",
    ),
    "cyclist": (r"cyclists?", r"bicycl(?:e|es|ist|ists)", r"bikers?", r"xe đạp"),
    "motorcycle": (
        r"motorcycles?",
        r"motorbikes?",
        r"scooters?",
        r"mopeds?",
        r"xe máy",
        r"xe mô tô",
    ),
    "car": (
        r"cars?",
        r"sedans?",
        r"suvs?",
        r"vehicles?",
        r"hatchbacks?",
        r"ô tô",
        r"xe hơi",
        r"xe con",
    ),
    "truck": (r"trucks?", r"lorr(?:y|ies)", r"semi-?trailers?", r"vans?", r"xe tải"),
    "bus": (r"buses", r"busses", r"bus", r"coaches?", r"xe buýt"),
    "traffic_light": (
        r"traffic lights?",
        r"traffic signals?",
        r"stop ?lights?",
        r"đèn giao thông",
        r"đèn đỏ",
        r"đèn tín hiệu",
    ),
    # Weather
    "rain": (
        r"rain",
        r"rainy",
        r"raining",
        r"rainfall",
        r"drizzl(?:e|ing)",
        r"downpour",
        r"puddles?",
        r"windshield wipers?",
        r"wipers?",
        r"trời mưa",
        r"mưa",
    ),
    "snow": (
        r"snow",
        r"snowy",
        r"snowing",
        r"snowfall",
        r"snow-?covered",
        r"slush",
        r"wintry",
        r"tuyết",
    ),
    "fog": (r"fog", r"foggy", r"mist", r"misty", r"haze", r"hazy", r"sương mù"),
    "overcast": (
        r"overcast",
        r"cloudy",
        r"grey sky",
        r"gray sky",
        r"grey clouds",
        r"gray clouds",
        r"nhiều mây",
    ),
    "clear_sky": (
        r"clear (?:blue )?sky",
        r"sunny",
        r"blue skies?",
        r"bright sunlight",
        r"trời nắng",
        r"nắng",
    ),
    # Time of day
    "night": (
        r"night",
        r"night-?time",
        r"after dark",
        r"darkness",
        r"ban đêm",
        r"buổi tối",
        r"đêm",
    ),
    "day": (r"daytime", r"daylight", r"broad daylight", r"during the day", r"ban ngày"),
    "dusk": (r"dusk", r"twilight", r"sunset", r"golden hour", r"evening", r"hoàng hôn"),
    "dawn": (r"dawn", r"sunrise", r"early morning", r"bình minh"),
    # Place and road
    "highway": (
        r"highways?",
        r"freeways?",
        r"motorways?",
        r"expressways?",
        r"interstates?",
        r"đường cao tốc",
        r"cao tốc",
    ),
    "intersection": (
        r"intersections?",
        r"junctions?",
        r"crossroads?",
        r"roundabouts?",
        r"giao lộ",
        r"ngã tư",
    ),
    "tunnel": (r"tunnels?", r"underpass(?:es)?", r"đường hầm", r"hầm"),
    "residential": (r"residential", r"suburban", r"neighbou?rhood", r"houses", r"khu dân cư"),
    "urban": (r"urban", r"downtown", r"city street", r"city centre", r"city center", r"nội thành"),
    "parking": (r"parking lots?", r"car ?parks?", r"parking garages?", r"parked", r"bãi đỗ xe"),
    "construction": (
        r"construction",
        r"road ?works?",
        r"traffic cones?",
        r"barriers?",
        r"công trường",
    ),
    "wet_road": (
        r"wet (?:road|pavement|asphalt|street|surface)",
        r"slick (?:road|pavement)",
        r"đường ướt",
    ),
    "traffic_jam": (
        r"traffic jam",
        r"congestion",
        r"congested",
        r"bumper[- ]to[- ]bumper",
        r"stopped traffic",
        r"tắc đường",
        r"ùn tắc",
    ),
}

# Words that assert emptiness rather than naming what is absent. "An empty
# residential street" is a request to exclude people, and treating it as one is
# what makes the phrase mean anything. The inference is safe because every
# exclusion is reported back in the response and rendered as a removable chip, so
# a user who meant something else can see it and take it off.
_IMPLIED_EXCLUSIONS: dict[str, tuple[str, ...]] = {
    "people": (r"empty", r"deserted", r"desolate", r"abandoned", r"vắng", r"không người"),
}

_COMPILED_IMPLIED = {
    concept: re.compile(r"(?<![\w-])(?:" + "|".join(patterns) + r")(?![\w-])", re.IGNORECASE)
    for concept, patterns in _IMPLIED_EXCLUSIONS.items()
}

# Cues that flip the meaning of a *following* mention. Ordered longest-first at
# compile time so "no visible" wins over "no".
_NEGATION_CUES: tuple[str, ...] = (
    r"no other",
    r"no visible",
    r"no discernible",
    r"no apparent",
    r"none of",
    r"no signs? of",
    r"no evidence of",
    r"free of",
    r"devoid of",
    r"empty of",
    r"absence of",
    r"absent of",
    r"lack(?:ing|s)? (?:of|any)?",
    r"without",
    r"nobody",
    r"no one",
    r"noone",
    r"neither",
    r"nor",
    r"unoccupied",
    r"deserted",
    r"empty",
    r"clear of",
    r"no",
    r"not",
    r"zero",
)

# Cues that negate what comes *before* them. English puts the predicate after the
# subject, so "pedestrians are not visible" names the thing first and denies it
# second -- a forward-only scope reads that caption as confirming pedestrians,
# which is exactly backwards. Kept separate from the forward cues, and matched
# first, because the forward cue "not" sits inside several of these.
_BACKWARD_NEGATION_CUES: tuple[str, ...] = (
    r"are not visible",
    r"is not visible",
    r"aren'?t visible",
    r"isn'?t visible",
    r"are not present",
    r"is not present",
    r"are not seen",
    r"is not seen",
    r"are not in sight",
    r"is not in sight",
    r"are absent",
    r"is absent",
    r"cannot be seen",
    r"can'?t be seen",
    r"could not be seen",
    r"are nowhere to be seen",
    r"is nowhere to be seen",
    r"are missing",
    r"is missing",
    r"not visible",
    r"not present",
)

# A negation cue stops applying at a clause boundary or a contrast word. Without
# terminators, one "no" near the start of a 768-character caption would negate
# every concept in the rest of it.
_SCOPE_TERMINATORS = re.compile(
    r"[.;:!?]|,|\bbut\b|\bhowever\b|\byet\b|\balthough\b|\bthough\b|\bwhile\b|\bwhereas\b|\bdespite\b|\bexcept\b|—|–"
)

# Query-side markers introducing an exclusion. Vietnamese is included because the
# product accepts Vietnamese queries untransliterated (MVP definition of done
# step 2), and "không có người" is the natural way to write "without people".
_QUERY_NEGATION = re.compile(
    r"\b(?:without|excluding|except(?:\s+for)?|minus|no|not)\b"
    r"|\bkhông\s+có\b|\bkhông\b|\btrừ\b|\bngoại\s+trừ\b",
    re.IGNORECASE,
)

# Left behind when an exclusion clause is cut out of the middle of a sentence
# ("night driving with no pedestrians" leaves a trailing "with"). Harmless to the
# encoder but it shows up in the UI, which echoes the interpreted query back.
_DANGLING_TAIL = re.compile(
    r"\s*\b(?:with|containing|showing|during|and|or|in|on|at|a|an|the|của|có)\b\s*$",
    re.IGNORECASE,
)

# Coordinators that continue an exclusion list: in "without people or cyclists",
# the exclusion covers both. A plain "and"/"with" ends it.
_EXCLUSION_CONTINUATION = re.compile(r"^\s*(?:or|nor|and|,)\s+", re.IGNORECASE)

# Ends an exclusion clause and returns the query to positive assertions.
_EXCLUSION_TERMINATOR = re.compile(
    r"\b(?:with|containing|showing|during|on a|in a)\b", re.IGNORECASE
)

_COMPILED_CONCEPTS: dict[str, re.Pattern[str]] = {
    name: re.compile(r"(?<![\w-])(?:" + "|".join(patterns) + r")(?![\w-])", re.IGNORECASE)
    for name, patterns in _CONCEPT_PATTERNS.items()
}

_COMPILED_NEGATION = re.compile(
    r"(?<![\w-])(?:" + "|".join(sorted(_NEGATION_CUES, key=len, reverse=True)) + r")(?![\w-])",
    re.IGNORECASE,
)

_COMPILED_BACKWARD_NEGATION = re.compile(
    r"(?<![\w-])(?:"
    + "|".join(sorted(_BACKWARD_NEGATION_CUES, key=len, reverse=True))
    + r")(?![\w-])",
    re.IGNORECASE,
)

# English phrases to embed when the typed query is not in the encoder's
# language. SigLIP was not trained on Vietnamese, so "trời mưa" scores like an
# out-of-domain subject and the similarity floor drops the whole answer. The
# lexicon already mapped that query onto concepts; these glosses are what the
# visual tower actually understands.
_CONCEPT_EMBED_GLOSS: dict[str, str] = {
    "people": "pedestrians people walking",
    "cyclist": "cyclist bicycle",
    "motorcycle": "motorcycle motorbike",
    "car": "car vehicle",
    "truck": "truck van",
    "bus": "bus",
    "traffic_light": "traffic light",
    "rain": "rainy weather rain",
    "snow": "snowy snow",
    "fog": "fog foggy",
    "overcast": "overcast cloudy",
    "clear_sky": "sunny clear sky",
    "night": "night nighttime",
    "day": "daytime daylight",
    "dusk": "dusk sunset",
    "dawn": "dawn sunrise",
    "highway": "highway freeway",
    "intersection": "intersection crossroads",
    "tunnel": "tunnel",
    "residential": "residential street houses",
    "urban": "urban city street",
    "parking": "parking lot",
    "construction": "road construction",
    "wet_road": "wet road",
    "traffic_jam": "traffic jam congestion",
}


def _has_non_ascii_letters(text: str) -> bool:
    """True when the query uses letters outside basic English A–Z.

    Vietnamese is written in Latin script, so an ASCII-letter ratio cannot tell
    it from English. Diacritics (ờ, ư, ă, …) are the reliable signal that the
    visual tower's English embedding space will not match the typed string.
    """

    return any(char.isalpha() and not ("A" <= char <= "Z" or "a" <= char <= "z") for char in text)


def concept_names() -> tuple[str, ...]:
    """Every concept the lexical path can recall exhaustively."""

    return tuple(_COMPILED_CONCEPTS)


@dataclass(frozen=True)
class ParsedQuery:
    """A query split into what the encoder sees and what the logic enforces.

    ``embedding_text`` is what gets embedded (English glosses when the typed
    query is not Latin-script). ``semantic_text`` is the query with exclusion
    clauses stripped out. Embedding "a rainy day without people" whole is a known
    failure mode of contrastive encoders: they have no representation for
    negation, so the phrase lands *nearer* to frames containing people than the
    positive part alone would. The exclusion is enforced by
    :data:`excluded` instead, where it can actually be evaluated.
    """

    raw: str
    semantic_text: str
    required: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    # Terms the user typed that no concept covers. Kept for reporting so the UI
    # can say which part of a sentence was handled semantically only.
    unmatched_exclusions: tuple[str, ...] = ()

    @property
    def has_concepts(self) -> bool:
        """True when the lexical path can guarantee a complete answer set.

        Only concept-backed queries can be answered exhaustively: completeness
        comes from scanning every caption for a known surface form, and a phrase
        with no known form has nothing to scan for.
        """

        return bool(self.required or self.excluded)

    @property
    def embedding_text(self) -> str:
        """Text actually sent to the visual / caption towers.

        English queries pass through as ``semantic_text``, minus surface forms of
        concepts that are no longer required -- otherwise removing a filter chip
        would leave the encoder still looking for that concept. A Vietnamese (or
        otherwise non-Latin) query is replaced by English glosses of the
        remaining required concepts, because those towers share an English
        image-text space.
        """

        if _has_non_ascii_letters(self.semantic_text):
            gloss = " ".join(concept_embed_gloss(concept) for concept in self.required)
            return gloss or self.semantic_text
        return _english_embedding_text(self.semantic_text, self.required)


def concept_embed_gloss(concept: str) -> str:
    """English phrase the visual tower understands for a lexicon concept."""

    return _CONCEPT_EMBED_GLOSS.get(concept, concept.replace("_", " "))


def _english_embedding_text(semantic_text: str, required: tuple[str, ...]) -> str:
    """Drop surface forms of concepts the caller is no longer requiring.

    ``required`` is what the UI chips represent. If a chip is removed, those
    words must leave the embedding, not only the caption filter, or the visual
    ranking cannot widen.
    """

    kept = set(required)
    stripped = semantic_text
    for concept, pattern in _COMPILED_CONCEPTS.items():
        if concept in kept:
            continue
        stripped = pattern.sub(" ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip(" ,.-")
    if stripped:
        return stripped
    if required:
        return " ".join(concept_embed_gloss(concept) for concept in required)
    return semantic_text


def concepts_in_phrase(phrase: str) -> tuple[str, ...]:
    """Canonical concepts mentioned in a fragment of user text."""

    return tuple(name for name, pattern in _COMPILED_CONCEPTS.items() if pattern.search(phrase))


def parse_query(text: str) -> ParsedQuery:
    """Split a natural-language query into a semantic part and hard constraints.

    Exclusions are detected from negation markers and mapped onto concepts.
    Required concepts are read from whatever remains, which makes them a
    *preference plus a completeness guarantee* rather than a filter: a frame that
    matches semantically but whose caption never names the concept is still
    returned, it simply is not part of the guaranteed set.
    """

    raw = text.strip()
    if not raw:
        raise ValueError("query must not be empty")

    excluded: list[str] = []
    unmatched: list[str] = []
    positive_parts: list[str] = []

    cursor = 0
    while cursor < len(raw):
        match = _QUERY_NEGATION.search(raw, cursor)
        if match is None:
            positive_parts.append(raw[cursor:])
            break

        positive_parts.append(raw[cursor : match.start()])

        # The exclusion runs from the marker to whichever comes first: a word
        # that resumes positive assertion, or the end of the query.
        remainder = raw[match.end() :]
        stop = _EXCLUSION_TERMINATOR.search(remainder)
        clause = remainder[: stop.start()] if stop else remainder

        found = concepts_in_phrase(clause)
        if found:
            excluded.extend(found)
        else:
            stripped = _EXCLUSION_CONTINUATION.sub("", clause).strip(" ,.")
            if stripped:
                unmatched.append(stripped)

        cursor = match.end() + (stop.start() if stop else len(remainder))

    semantic_text = re.sub(r"\s+", " ", " ".join(positive_parts)).strip(" ,.-")
    while True:
        trimmed = _DANGLING_TAIL.sub("", semantic_text).strip(" ,.-")
        if trimmed == semantic_text:
            break
        semantic_text = trimmed
    # A query that was nothing but an exclusion ("without people") still needs
    # something to embed, or the ANN stage has no query at all.
    if not semantic_text:
        semantic_text = raw

    for concept, pattern in _COMPILED_IMPLIED.items():
        if concept not in excluded and pattern.search(semantic_text):
            excluded.append(concept)

    required = tuple(
        dict.fromkeys(c for c in concepts_in_phrase(semantic_text) if c not in excluded)
    )

    return ParsedQuery(
        raw=raw,
        semantic_text=semantic_text,
        required=required,
        excluded=tuple(dict.fromkeys(excluded)),
        unmatched_exclusions=tuple(unmatched),
    )


@dataclass(frozen=True, slots=True)
class Clause:
    """A span of caption text and whether a negation cue governs it."""

    text: str
    negated: bool


def split_clauses(caption: str) -> tuple[Clause, ...]:
    """Split a caption into negation scopes.

    A cue negates the rest of its own clause. A following clause that begins with
    a coordinator inherits the negation, so "no pedestrians or cyclists" marks
    both as absent rather than only the first.

    Split once and reused for every concept: this is by far the most expensive
    step in caption matching -- around 80% of it -- and the result depends only on
    the caption, so recomputing it per concept was pure waste. Callers with many
    concepts to test should hold the result (see :mod:`search.catalog`).
    """

    pieces = [piece for piece in _SCOPE_TERMINATORS.split(caption) if piece and piece.strip()]
    clauses: list[Clause] = []
    inherited = False
    for piece in pieces:
        cue = _COMPILED_NEGATION.search(piece)
        trailing = _COMPILED_BACKWARD_NEGATION.search(piece)

        # A post-posed cue wins when it starts no later than the forward one,
        # because the forward cue is usually the "not" inside it.
        if trailing is not None and (cue is None or trailing.start() <= cue.start()):
            subject = piece[: trailing.start()]
            if subject.strip():
                clauses.append(Clause(subject, True))
            remainder = piece[trailing.end() :]
            if remainder.strip():
                clauses.append(Clause(remainder, False))
            inherited = False
            continue

        if cue is not None:
            # Text before the cue is not in its scope and is treated as its own
            # non-negated clause, so "cars are parked and no people are around"
            # does not mark cars absent.
            head = piece[: cue.start()]
            if head.strip():
                clauses.append(Clause(head, False))
            clauses.append(Clause(piece[cue.start() :], True))
            inherited = True
            continue

        continues_list = bool(_EXCLUSION_CONTINUATION.match(piece))
        clauses.append(Clause(piece, inherited and continues_list))
        if not continues_list:
            inherited = False
    return tuple(clauses)


def concept_pattern(concept: str) -> re.Pattern[str]:
    """Compiled surface forms for a concept.

    An unknown concept falls back to its literal form, so a caller can constrain
    on a word the lexicon has never heard of and get sensible behaviour rather
    than a silent no-op.
    """

    pattern = _COMPILED_CONCEPTS.get(concept)
    if pattern is None:
        pattern = re.compile(rf"(?<![\w-]){re.escape(concept)}s?(?![\w-])", re.IGNORECASE)
    return pattern


def resolve_concept(clauses: tuple[Clause, ...], concept: str) -> tuple[Polarity, int]:
    """Resolve a concept against pre-split clauses.

    Returns the polarity and how many times the concept is mentioned outside a
    negation scope. That count is evidence strength: a caption discussing snow
    four times is more about snow than one that names it in passing, and ranking
    needs some way to tell them apart.
    """

    pattern = concept_pattern(concept)
    mentions = 0
    saw_negated = False
    for clause in clauses:
        found = len(pattern.findall(clause.text))
        if not found:
            continue
        if clause.negated:
            saw_negated = True
        else:
            mentions += found
    if mentions:
        return "present", mentions
    if saw_negated:
        return "absent", 0
    return "unknown", 0


def caption_polarity(caption: str, concept: str) -> Polarity:
    """Resolve what a caption says about a concept.

    ``present`` when it is mentioned outside a negation scope, ``absent`` when
    every mention is negated, and ``unknown`` when it is never mentioned. The
    distinction between ``absent`` and ``unknown`` matters: absence was observed
    and reported, whereas unknown only means the caption did not comment.
    """

    return resolve_concept(split_clauses(caption), concept)[0]


@dataclass
class CaptionVerdict:
    """Whether a caption satisfies a parsed query's hard constraints."""

    admissible: bool
    # Required concepts the caption positively confirms. Drives lexical ranking:
    # a caption confirming two of two beats one confirming one of two.
    confirmed: tuple[str, ...] = field(default_factory=tuple)
    # Excluded concepts the caption explicitly reports as absent. Stronger
    # evidence than silence, and ranked above it.
    denied: tuple[str, ...] = field(default_factory=tuple)
    # Total unnegated mentions of the required concepts. Evidence strength, used
    # for ranking only.
    mentions: int = 0


def evaluate_clauses(clauses: tuple[Clause, ...], parsed: ParsedQuery) -> CaptionVerdict:
    """Apply a parsed query's constraints to pre-split caption clauses.

    Rejection is deliberately asymmetric, and the asymmetry is the whole point:

    * An excluded concept that is **present** rejects the frame. This is what
      makes "without people" mean something.
    * An excluded concept that is **unknown** does not reject. Captions are
      summaries, not exhaustive inventories, so silence is not proof of presence
      and treating it as such would empty the result set.
    * A required concept that is explicitly **absent** rejects the frame -- a
      caption saying "no snow" is not a match for "snowy", however close its
      vector happens to land.
    """

    confirmed: list[str] = []
    denied: list[str] = []
    mentions = 0

    for concept in parsed.excluded:
        polarity, _ = resolve_concept(clauses, concept)
        if polarity == "present":
            return CaptionVerdict(admissible=False)
        if polarity == "absent":
            denied.append(concept)

    for concept in parsed.required:
        polarity, found = resolve_concept(clauses, concept)
        if polarity == "absent":
            return CaptionVerdict(admissible=False)
        if polarity == "present":
            confirmed.append(concept)
            mentions += found

    return CaptionVerdict(
        admissible=True,
        confirmed=tuple(confirmed),
        denied=tuple(denied),
        mentions=mentions,
    )


def evaluate_caption(caption: str, parsed: ParsedQuery) -> CaptionVerdict:
    """Apply a parsed query's constraints to one keyframe caption."""

    return evaluate_clauses(split_clauses(caption), parsed)


__all__ = [
    "CaptionVerdict",
    "Clause",
    "ParsedQuery",
    "Polarity",
    "caption_polarity",
    "concept_names",
    "concept_pattern",
    "concepts_in_phrase",
    "evaluate_caption",
    "evaluate_clauses",
    "parse_query",
    "resolve_concept",
    "split_clauses",
]
