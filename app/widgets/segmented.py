"""Deux boutons collés sous une seule bordure : un contrôle segmenté.

La ligne de tête du bandeau manque de place, et « Fetch » séparé de son ⊘ (ou « Script » de son 🛠)
coûte 8 px d'écart de layout pour deux actions qui vont ensemble. Le conteneur compte comme un seul
item du `FlowLayout` : l'écart disparait, et la bordure commune est le bord gauche du segment de
droite.

Le conteneur ne peint volontairement rien : chaque moitié garde son propre fond et ses propres
états (survol, enfoncé, accentué, grisé, coché). Une règle descendante du `.qss` qui colorerait le
conteneur imposerait le style de l'un à l'autre, et une moitié accentuée déborderait des coins
arrondis.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QWidget


class SegmentedControl(QFrame):
    """Conteneur transparent de deux boutons collés : ni fond, ni bordure, aucun espace intérieur.

    Classe distincte de `QFrame` pour que le bandeau puisse la reconnaitre : un double-clic sur le
    joint des deux boutons ne doit jamais plier le bandeau.
    """


def segmented(object_name: str, *buttons: QWidget) -> SegmentedControl:
    """Colle les boutons bord à bord, à la hauteur du plus haut d'entre eux.

    Sans la politique verticale `Expanding`, un `QToolButton` (hauteur fixe) reste plus court que le
    `QPushButton` voisin et sa boite flotte au milieu du groupe : deux hauteurs visibles au lieu
    d'une seule bordure.
    """
    holder = SegmentedControl()
    holder.setObjectName(object_name)
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for button in buttons:
        policy = button.sizePolicy()
        policy.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        button.setSizePolicy(policy)
        layout.addWidget(button)
    return holder
