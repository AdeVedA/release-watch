"""Decoupage des notes GitHub et tailles lisibles : logique pure, sans fenetre."""

from __future__ import annotations

import pytest

from app import notes_parse
from app.widgets.notes_dock import human_size
from tests.sample import NOTES_WITH_CONTRIBUTORS


def test_les_contributeurs_sortent_du_corps() -> None:
    parts = notes_parse.split_notes(NOTES_WITH_CONTRIBUTORS)
    assert "@alice" not in parts.body, "la section contributeurs est restee dans le corps"
    assert parts.contributors, "aucune section contributeurs detectee"
    assert parts.has_contributors
    assert "Full Changelog" in parts.body, "le lien Full Changelog a ete perdu du corps"


def test_pas_de_fausse_section_contributeurs() -> None:
    assert not notes_parse.split_notes("## 1.0\n\nrien\n").contributors


def test_balises_html_retirees_du_corps() -> None:
    details = notes_parse.split_notes("<details open>\n\nnote A\n\n</details>\n")
    assert details.body.strip() == "note A", f"balises details/summary non retirees : {details.body!r}"


def test_full_changelog_garde_apres_une_section_contributeurs() -> None:
    brut = "## 6.9.0\n\n## New Contributors\n\n- @alice\n\n**Full Changelog**: https://github.com/x/y\n"
    assert "Full Changelog" in notes_parse.split_notes(brut).body


@pytest.mark.parametrize("titre", ["## New Contributors", "## Nouveaux contributeurs", "## Contributors"])
def test_titres_de_section_contributeurs_reconnus(titre: str) -> None:
    brut = f"## 1.0\n\n- correctif\n\n{titre}\n\n- @alice\n"
    assert notes_parse.split_notes(brut).contributors, f"section non detectee : {titre!r}"


def test_notes_vides_ne_cassent_rien() -> None:
    for brut in ("", "\n\n", "   \n"):
        parts = notes_parse.split_notes(brut)
        assert not parts.contributors


@pytest.mark.parametrize(
    ("octets", "attendu"),
    [
        (0, "taille inconnue"),
        (-1, "taille inconnue"),
        (1, "1 octet"),
        (1023, "1023 octets"),
    ],
)
def test_taille_lisible_petites_valeurs(octets: int, attendu: str) -> None:
    assert human_size(octets) == attendu


@pytest.mark.parametrize(
    ("octets", "unite"),
    [
        (2048, "Ko"),
        (5 * 1024 * 1024, "Mo"),
        (3 * 1024 * 1024 * 1024, "Go"),
    ],
)
def test_taille_lisible_unite_choisie(octets: int, unite: str) -> None:
    """L'unite doit rester celle qui garde un nombre lisible (1.0 a 1023.9)."""
    texte = human_size(octets)
    assert texte.endswith(unite), f"{octets} octets -> {texte!r}, attendu une taille en {unite}"
    nombre = float(texte.split()[0])
    assert 1.0 <= nombre < 1024.0, f"{octets} octets -> {texte!r}"


TAILLES_LIMITES: tuple[tuple[int, str], ...] = (
    (900 * 1024, "900.0 Ko"),  # ancien rendu faux : 0.9 Mo
    (65432100, "62.4 Mo"),  # ancien rendu faux : 0.1 Go
    (65 * 1024 * 1024 * 1024, "65.0 Go"),  # ancien rendu faux : 69793218560.0 octets
)


@pytest.mark.parametrize(("octets", "attendu"), TAILLES_LIMITES)
def test_taille_lisible_ne_gonfle_pas_d_un_cran(octets: int, attendu: str) -> None:
    assert human_size(octets) == attendu, f"{octets} octets -> {human_size(octets)!r}"
