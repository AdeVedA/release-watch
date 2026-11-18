"""Règles de filtrage (tags et assets) saisies par bandeau.

Module feuille : stdlib + `app/i18n.py`, ni Qt ni réseau. Il est donc utilisable
par les modèles, par les widgets et par les contrôles hors écran.

Deux syntaxes, dans le même champ :
- glob par défaut : `v6.*` (préfixe), `*.whl` (suffixe), `*debug*` (chaîne),
  et les caractères `- _ . ,` sont des caractères normaux ;
- `re:` devant le motif pour basculer en regex recherchée partiellement.

Plusieurs motifs dans un champ sont séparés par point-virgule. La virgule reste
donc un caractère légitime d'un nom de tag ou d'asset.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from fnmatch import fnmatchcase
from typing import Final

from app.i18n import t

REGEX_PREFIX: Final[str] = "re:"
RULE_SEPARATOR: Final[str] = ";"
MAX_RULES: Final[int] = 12
MAX_RULE_LENGTH: Final[int] = 200


def split_rules(raw: str) -> list[str]:
    """Découpe un champ de regles. Une règle vide = aucune regle."""
    return [part.strip() for part in raw.split(RULE_SEPARATOR) if part.strip()]


def has_rules(raw: str) -> bool:
    return bool(split_rules(raw))


def rules_error(raw: str) -> str:
    """Chaîne vide si tout est compilable, sinon le message court à afficher."""
    rules = split_rules(raw)
    if len(rules) > MAX_RULES:
        return t("trop de motifs ({count}), maximum {limit}").format(count=len(rules), limit=MAX_RULES)
    for rule in rules:
        if len(rule) > MAX_RULE_LENGTH:
            return t("motif trop long ({length} caractères), maximum {limit}").format(
                length=len(rule), limit=MAX_RULE_LENGTH
            )
        if rule.startswith(REGEX_PREFIX):
            pattern = rule[len(REGEX_PREFIX) :].strip()
            if not pattern:
                return t("'re:' suivi d'une regex attendue")
            try:
                re.compile(pattern)
            except re.error as exc:
                return t("regex invalide '{pattern}' : {exc}").format(pattern=pattern, exc=exc)
    return ""


def _matcher(rule: str) -> re.Pattern[str] | None:
    if not rule.startswith(REGEX_PREFIX):
        return None
    return re.compile(rule[len(REGEX_PREFIX) :].strip())


def matches(raw: str, value: str) -> bool:
    """Vrai si `value` satisfait au moins un motif de `raw`. Champ vide = aucune correspondance."""
    text = value.strip()
    for rule in split_rules(raw):
        pattern = _matcher(rule)
        if pattern is not None:
            if pattern.search(text) is not None:
                return True
        elif fnmatchcase(text, rule):
            return True
    return False


def keep(value: str, include: str, exclude: str) -> bool:
    """Vrai si `value` passe le couple de règles. Inclure vide = tout est accepté."""
    if has_rules(include) and not matches(include, value):
        return False
    return not matches(exclude, value)


def filter_names(names: Sequence[str], include: str, exclude: str) -> list[str]:
    """Motifs autorisés seulement, dans l'ordre d'origine."""
    return [name for name in names if keep(name, include, exclude)]
