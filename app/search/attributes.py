"""Conservative color/object relations, scoped to one caption clause."""

import re
from dataclasses import dataclass

from search.query import Polarity, split_clauses

_COLORS = r"red|yellow|blue|green|white|black|orange|gray|grey|brown"
_OBJECTS = r"trucks?|cars?|buses|bus|vans?|motorcycles?|bicycles?"
_BEFORE = re.compile(rf"\b({_COLORS})\s+(?:(?:small|large|parked|moving)\s+)?({_OBJECTS})\b", re.I)
_AFTER = re.compile(
    rf"\b({_OBJECTS})\s+(?:(?:that\s+|which\s+)?(?:is|are)\s+|(?:colored|coloured)\s+)?({_COLORS})\b",
    re.I,
)


@dataclass(frozen=True, order=True)
class ColorRelation:
    subject: str
    color: str

    @property
    def label(self) -> str:
        return f"{self.color}:{self.subject}"


def _relation(subject: str, color: str) -> ColorRelation:
    subject = subject.casefold()
    return ColorRelation(
        "bus" if subject in ("bus", "buses") else subject.removesuffix("s"),
        color.casefold().replace("grey", "gray"),
    )


def color_relations(text: str) -> tuple[ColorRelation, ...]:
    return tuple(
        sorted(
            {_relation(subject, color) for color, subject in _BEFORE.findall(text)}
            | {_relation(subject, color) for subject, color in _AFTER.findall(text)}
        )
    )


def unresolved_colors(text: str) -> tuple[str, ...]:
    bound_spans = {match.span(1) for match in _BEFORE.finditer(text)} | {
        match.span(2) for match in _AFTER.finditer(text)
    }
    return tuple(
        sorted(
            {
                match.group().casefold().replace("grey", "gray")
                for match in re.finditer(rf"\b({_COLORS})\b", text, re.I)
                if match.span() not in bound_spans
            }
        )
    )


def relation_polarity(caption: str, relation: ColorRelation) -> Polarity:
    positive, negative = set(), set()
    for clause in split_clauses(caption):
        (negative if clause.negated else positive).update(color_relations(clause.text))
    if relation in positive:
        return "present"
    if relation in negative or any(other.subject == relation.subject for other in positive):
        return "absent"
    return "unknown"
