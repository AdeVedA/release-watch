"""Source unique de vérité des couleurs et des dimensions.

C'est LE seul fichier du projet où une valeur de couleur est écrite.
Aucun hexadécimal ne doit apparaître dans un `.qss` ni ailleurs dans le code Python :
les feuilles de style référencent des tokens (`$nom`) résolus ici.

Pour changer une couleur : éditer `DARK` (ou `SIZES`) puis Ctrl+Shift+P dans
l'application (`theme.reload_theme` recharge ce module et le `.qss` sans redémarrer).

Les tokens sont des identifiants Python (lettres, chiffres, underscore) car la
syntaxe de substitution est celle de `string.Template`.
"""

from __future__ import annotations

TOKENS_COLORS: dict[str, str] = {
    # Fonds
    "bg_window": "#15171b",
    "bg_panel": "#1d2025",
    "bg_banner": "#22262d",
    "bg_banner_alt": "#272c34",
    "bg_input": "#171a1f",
    "bg_hover": "#2c323b",
    "bg_selected": "#33404f",
    "bg_disabled": "#1b1e23",
    "bg_menu": "#1f2329",
    "bg_dock": "#1b1e23",
    "bg_tooltip": "#101215",
    "bg_scroll_track": "#191c21",
    "bg_scroll_handle": "#3a424d",
    "bg_selection": "#2f4a63",
    "bg_badge": "#2b313a",
    "bg_button": "#2e4d6f",
    # Bordures
    "border": "#3a414b",
    "border_strong": "#586474",
    "border_focus": "#4b7fb5",
    "border_banner": "#2c333c",
    # Polices
    "fg_text": "#e6e9ee",
    "fg_title": "#f4f7fb",
    "fg_title2": "#fffab4",
    "fg_button_title": "#7bba9c",
    "fg_dim": "#abbbcf",  # #9aa4b1
    "fg_muted": "#92a1b6",  # #6f7a88
    "fg_disabled": "#6e7a8a",
    "fg_link": "#6cb0e8",
    "fg_on_accent": "#0f1318",
    # Couleurs semi-symboliques
    "accent": "#4f8ecf",
    "accent_hover": "#63a4e6",
    # Etats
    "ok": "#4faa78",
    "ok_soft": "#2c5741",
    "new": "#d8b23c",
    "new_soft": "#5c4c1c",
    "ahead": "#5aa9d6",
    "ahead_soft": "#2c4a5c",
    "unknown": "#7c8794",
    "unknown_soft": "#333a43",
    "err": "#d75c5c",
    "err_soft": "#5c2b2b",
}

TOKENS_SIZES: dict[str, str] = {
    "font_family": '"Segoe UI", "Noto Sans", sans-serif',
    "fs_xs": "12px",
    "fs_sm": "13px",
    "fs_md": "14px",
    "fs_lg": "16px",
    "fs_xl": "19px",
    # Cran de taille du titre de bandeau quand le nom ne tient pas en fs_xl.
    # Chaque cran a sa règle QSS `#bannerTitle[fsize="lg"]` / `#bannerTitle[fsize="md"]` :
    # la borne basse du raccourcissement vient donc de la palette, pas d'une constante Python.
    "fs_title_lg": "16px",
    "fs_title_md": "14px",
    # Échelle de taille pour le panneau de description (Ctrl+molette).
    # Chaque cran a sa règle QSS `#txtNotes[fsize="12"]` : la borne basse et la
    # borne haute du clampage viennent donc de la palette, pas d'une constante Python.
    "fs_notes_12": "12px",
    "fs_notes_13": "13px",
    "fs_notes_14": "14px",
    "fs_notes_15": "15px",
    "fs_notes_16": "16px",
    "fs_notes_17": "17px",
    "fs_notes_18": "18px",
    "radius_s": "4px",
    "radius_m": "7px",
    "radius_l": "11px",
    "pad_xs": "2px",
    "pad_sm": "3px",
    "pad_md": "9px",
    "pad_lg": "14px",
    # Padding interne d'un bandeau : le QSS est la seule source (le layout ne met aucune marge).
    "pad_banner_v": "4px",
    "pad_banner_h": "14px",
    # Espaces verticaux des lignes de réglages, lus en Python via `token_px()` : un `padding` QSS
    # sur ces conteneurs ne serait pas consulté, leurs layouts posent déjà leurs marges.
    "row_pad_v": "4px",
    "filters_gap_v": "4px",
    # Largeur commune des quatre champs de filtre : seule façon de faire tomber les boîtes
    # « à garder » / « sauf » l'une sous l'autre sur les deux lignes de réglages
    # (`RepoBanner._sync_filter_columns`).
    "w_filter_field": "190px",
    # Plancher des mêmes champs : le layout leur donne toujours `$w_filter_field`, mais sans ce
    # plancher plus bas le minimum du layout égalerait 190px et le bandeau ne pourrait plus
    # descendre sous cette largeur (fenêtre étroite : le bandeau dépasserait la fenêtre).
    "w_filter_field_min": "90px",
    # Le titre du bandeau ne se réduit pas : au-delà de ce plafond, il s'élide.
    "w_title_max": "420px",
    # Plafond du combo « par défaut » : il se dimensionne sur son contenu, ce plafond empêche
    # un nom d'asset à rallonge de déplacer le groupe central vers la ligne suivante.
    "w_asset_combo_max": "260px",
    # Plafond du panneau latéral : il ne doit pas affamer les bandeaux sur fenêtre étroite.
    "w_dock_notes_min": "320px",
    "w_dock_notes_max": "1080px",
    # Colonnes d'une ligne de version : plafond du texte, puis boutons alignés serrés.
    "row_w_version": "220px",
    "row_w_meta": "96px",
    "row_w_asset": "28px",
    "row_w_validate": "66px",
    "row_h_action": "20px",
    "row_h_release": "27px",
    "border_w": "1px",
    "banner_edge_w": "4px",
}

TOKENS: dict[str, str] = {**TOKENS_COLORS, **TOKENS_SIZES}
