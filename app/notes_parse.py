"""Découpage des notes de release écrites par GitHub.

Les notes sont du texte contrôlé par l'auteur du repo : les sections générées par
GitHub (« New Contributors », « Contributors », remerciements) sont séparées du
corps pour être affichées dépliantes, sans appel réseau supplémentaire.

Module feuille : stdlib uniquement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CONTRIBUTOR_HEADINGS: tuple[str, ...] = (
    "new contributors",
    "contributors",
    "thank you",
    "thanks",
    "nouveaux contributeurs",
    "contributeurs",
    "remerciements",
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# Balises bloquantes que GitHub écrit autour des notes générées (« <details open> »,
# « <summary> ») : rendu Qt = une ligne vide au début du panneau. Elles sont retirées,
# le texte qu'elles encadrent est gardé.
_BLOCK_TAG = re.compile(r"</?(?:details|summary|picture|source|img|div|p|br)\b[^>]*/?>", re.IGNORECASE)
# Ligne qui poursuit un élément de liste (rejetée en retrait) ou élément de liste.
_LIST_LINE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CONTINUATION_LINE = re.compile(r"^\s{2,}\S")


@dataclass(slots=True)
class NotesParts:
    body: str = ""
    contributors: list[tuple[str, str]] = field(default_factory=list)

    @property
    def has_contributors(self) -> bool:
        return any(text.strip() for _label, text in self.contributors)


def _heading_title(raw: str) -> str:
    return raw.strip().strip("#:").strip().casefold()


def _is_contributor_heading(title: str) -> bool:
    return title in CONTRIBUTOR_HEADINGS or any(
        title.startswith(known) and len(title) - len(known) <= 12 for known in CONTRIBUTOR_HEADINGS
    )


def split_notes(notes_md: str) -> NotesParts:
    """Corps sans les sections contributeurs, et ces sections (titre, markdown)."""
    lines = notes_md.replace("\r\n", "\n").split("\n")
    body: list[str] = []
    sections: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        match = _HEADING.match(lines[index])
        level = len(match.group(1)) if match else 0
        title = _heading_title(match.group(2)) if match else ""
        if match and _is_contributor_heading(title):
            block: list[str] = []
            index += 1
            while index < len(lines):
                line = lines[index]
                inner = _HEADING.match(line)
                if inner and len(inner.group(1)) <= level:
                    break
                # La liste de contribution s'arrête à la première ligne qui n'est ni
                # un élément, ni sa continuation : « **Full Changelog**: ... » reste au corps.
                if line.strip() and not _LIST_LINE.match(line) and not _CONTINUATION_LINE.match(line):
                    break
                block.append(line)
                index += 1
            text = "\n".join(block).strip()
            if text:
                sections.append((match.group(2).strip(), text))
            continue
        body.append(lines[index])
        index += 1
    return NotesParts(body=_clean_body("\n".join(body)), contributors=sections)


def _clean_body(text: str) -> str:
    """Enleve les balises bloquantes de GitHub, puis les blancs de bord."""
    return _BLOCK_TAG.sub("", text).strip()
