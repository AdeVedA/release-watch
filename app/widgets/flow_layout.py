"""Disposition horizontale qui passe à la ligne quand la largeur manque.

Les lignes de réglages du bandeau (filtres tags, filtres assets, infos) et les
lignes de versions tiennent rarement en une ligne quand la fenêtre est étroite ou
que le panneau latéral est ouvert. Sans ceci, le layout écrase les champs ou rejette
les boutons hors du bandeau : l'utilisateur ne voit plus l'action.

Deux règles font le travail :
- un item de politique Expanding (titre, labels élidés) absorbe l'espace restant de
  sa ligne et se retire en premier quand le manque de place oblige à compresser ;
- les items trop larges pour la ligne passent à la ligne suivante.

La hauteur d'une ligne repliée n'est pas déléguée au height-for-width de Qt : une
`QScrollArea` ne le consulte jamais. C'est le rôle de `apply_flow_height()`.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QSpacerItem, QWidget

SPACING_FLOOR = 0
DEFAULT_WEIGHT = 1


def _expands(item: QLayoutItem) -> bool:
    """Vrai si l'item peut s'étirer horizontalement (widget Expanding, ou stretch du layout)."""
    widget = item.widget()
    if widget is None:
        # Item sans widget : un stretch posé par add_stretch().
        return bool(item.expandingDirections() & Qt.Orientation.Horizontal)
    return widget.sizePolicy().horizontalPolicy() is QSizePolicy.Policy.Expanding


def _is_active(item: QLayoutItem) -> bool:
    widget = item.widget()
    return not (widget is not None and widget.isHidden())


def _is_fixed_spacer(item: QLayoutItem) -> bool:
    """Espaceur de largeur posée par Python (`add_fixed_spacer`) : un pur jeu graphique.

    Il ne doit jamais entrer dans `minimumSize()` : sa largeur n'est pas une contrainte, c'est
    un réglage. Un minimum qui le comprendrait ferait grimper le minimum du layout, donc celui du
    bandeau, et la fenêtre comme le panneau latéral refuseraient de rétrécir.
    """
    return item.widget() is None and not (item.expandingDirections() & Qt.Orientation.Horizontal)


class FlowLayout(QLayout):
    """Même principe qu'une `QHBoxLayout`, mais les items débordants passent à la ligne."""

    def __init__(self, parent: QWidget | None = None, spacing: int = -1) -> None:
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        if spacing >= 0:
            self.setSpacing(spacing)
        self._items: list[QLayoutItem] = []
        # Poids par item : un stretch de centrage est lourd pour que les champs
        # Expanding de la même ligne ne déplacent pas le centre.
        self._weights: dict[QLayoutItem, int] = {}
        # Alignement vertical par défaut de la ligne + exceptions par widget (voir `set_line_valign`).
        self._line_valign: tuple[Qt.AlignmentFlag, int] = (Qt.AlignmentFlag.AlignVCenter, 0)
        self._valign: dict[QLayoutItem, tuple[Qt.AlignmentFlag, int]] = {}

    # ------------------------------------------------------------------ contrat QLayout

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802
        self._items.append(item)
        self._weights[item] = DEFAULT_WEIGHT

    def add_stretch(self, weight: int = DEFAULT_WEIGHT) -> QSpacerItem:
        """Item élastique : il avale le reliquat de la ligne et pousse ce qui suit contre le bord droit."""
        spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.addItem(spacer)
        self._weights[spacer] = max(1, weight)
        return spacer

    def add_fixed_spacer(self) -> QSpacerItem:
        """Item de largeur posée par Python : c'est lui qui aligne une colonne d'une ligne à l'autre.

        Politique Fixed et non Expanding : le layout ne lui donne aucune part du surplus, il
        lui laisse exactement la largeur reçue par `set_fixed_spacer_width()`.
        """
        spacer = QSpacerItem(SPACING_FLOOR, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.addItem(spacer)
        return spacer

    def set_fixed_spacer_width(self, spacer: QSpacerItem, width: int) -> None:
        """Nouvelle largeur d'un espaceur fixe. Ne déclenche volontairement aucune réactivation.

        Appelée depuis `resizeEvent`, c'est-à-dire pendant que la passe de layout est en cours :
        invalider ici remettrait la passe en route par-dessus celle qui la déclenche, et le
        redimensionnement de la fenêtre ne suivrait plus la souris. Les appelants hors passe de
        layout appellent `invalidate()`/`activate()` eux-mêmes.
        """
        spacer.changeSize(max(SPACING_FLOOR, width), 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_line_valign(self, align: Qt.AlignmentFlag, reserve: int = 0) -> None:
        """Alignement vertical de toute la ligne. Le `.qss` ne positionne jamais un widget : seul ici.

        La réserve est l'espace laissé sous chaque item ; elle compte dans la hauteur de ligne.
        """
        self._line_valign = (align, max(SPACING_FLOOR, reserve))
        self.invalidate()

    def set_valign(self, widget: QWidget, align: Qt.AlignmentFlag, reserve: int = 0) -> None:
        """Exception par widget : un bouton colle au bas de la ligne, ses voisins gardent de l'air."""
        for item in self._items:
            if item.widget() is widget:
                self._valign[item] = (align, max(SPACING_FLOOR, reserve))
                self.invalidate()
                return
        raise ValueError(f"widget absent du layout : {widget.objectName() or widget}")

    def _valign_of(self, item: QLayoutItem) -> tuple[Qt.AlignmentFlag, int]:
        return self._valign.get(item, self._line_valign)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:  # noqa: N802
        item = self._items.pop(index)
        self._weights.pop(item, None)
        return item
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        # Volontairement faux : la hauteur des lignes repliées est posée par
        # `apply_flow_height()`, seule chose que la `QScrollArea` respecte.
        return False

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._arrange(QRect(0, 0, width, 0), dry_run=True)

    def line_count(self, width: int) -> int:
        """Rangées qu'occuperaient les items à cette largeur : sert à décider si une ligne est repliée."""
        if width <= 0:
            return 0
        return len(self._lines(width))

    def natural_line(
        self,
        width: int,
        spacer: QSpacerItem,
        group_first: QWidget,
        group_last: QWidget,
        suffix_head: QWidget,
    ) -> tuple[int, int, int, int, int] | None:
        """Mesures naturelles de la ligne : (groupe_x_espaceur_a_zero, groupe, suffixe, place libre, écarts).

        Rien n'est lu sur la géométrie posée : les largeurs viennent des `sizeHint`/`minimumSize` des
        items, exactement comme les voit `_lines()`. Un appel peut donc poser l'espaceur AVANT la
        passe de layout, ce qui évite le va-et-vient visible (ligne qui se replie puis se
        déplie) quand la fenêtre change de taille.

        L'espaceur compte pour 0 dans ces mesures : c'est justement sa largeur que l'appelant
        doit choisir, et la lire aurait créé une dépendance circulaire.
        `None` si la ligne n'est pas dans l'état attendu (un repère est masqué ou hors du layout).
        """
        margins = self.contentsMargins()
        available = width - margins.left() - margins.right()
        if available <= 0:
            return None
        spacing = max(SPACING_FLOOR, self.spacing())
        active: list[QLayoutItem] = [item for item in self._items if _is_active(item)]
        index = self._slot_of(active, spacer)
        first = self._slot_of(active, group_first)
        last = self._slot_of(active, group_last)
        tail = self._slot_of(active, suffix_head)
        if index is None or first is None or last is None or tail is None:
            return None
        if not index < first <= last < tail:
            return None
        widths = [0 if item is spacer else self._width_of(item) for item in active]
        free = available - (sum(widths) + spacing * max(0, len(active) - 1))
        prefix = sum(widths[: index + 1]) + spacing * (index + 1)
        group = sum(widths[first : last + 1]) + spacing * (last - first)
        suffix = sum(widths[tail:]) + spacing * (len(active) - 1 - tail)
        return prefix, group, suffix, free, tail - last

    @staticmethod
    def _slot_of(active: list[QLayoutItem], reference: QWidget | QSpacerItem) -> int | None:
        """Position d'un widget (ou de l'espaceur lui-même) dans la suite des items actifs."""
        for position, item in enumerate(active):
            if item is reference or item.widget() is reference:
                return position
        return None

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._arrange(rect, dry_run=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        """Tout sur une ligne : c'est la largeur que le bandeau réclamera si la place est là."""
        margins = self.contentsMargins()
        spacing = max(SPACING_FLOOR, self.spacing())
        active_items = [item for item in self._items if _is_active(item)]
        natural = sum(self._width_of(item) for item in active_items)
        natural += spacing * max(0, len(active_items) - 1)
        width = natural + margins.left() + margins.right()
        return QSize(width, self._arrange(QRect(0, 0, width, 0), dry_run=True))

    def minimumSize(self) -> QSize:  # noqa: N802
        margins = self.contentsMargins()
        size = QSize()
        for item in self._items:
            if not _is_active(item) or _is_fixed_spacer(item):
                continue
            size = size.expandedTo(item.minimumSize())
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    # ------------------------------------------------------------------ agencement

    def _width_of(self, item: QLayoutItem) -> int:
        return max(item.minimumSize().width(), item.sizeHint().width())

    @staticmethod
    def _room_to_shrink(line: list[tuple[QLayoutItem, int]]) -> int:
        return sum(width - item.minimumSize().width() for item, width in line if _expands(item))

    def _lines(self, available: int) -> list[list[tuple[QLayoutItem, int]]]:
        """Répartit les items en lignes.

        Un item n'est rejeté sur la ligne suivante que si les items Expanding déjà
        présents ne peuvent pas assez se rétrécir pour le laisser passer : c'est ce
        qui garde les boutons d'action sur la ligne du titre.
        """
        spacing = max(SPACING_FLOOR, self.spacing())
        lines: list[list[tuple[QLayoutItem, int]]] = []
        current: list[tuple[QLayoutItem, int]] = []
        used = 0
        for item in self._items:
            if not _is_active(item):
                continue
            width = min(self._width_of(item), available)
            if not current:
                current.append((item, width))
                used = width
                continue
            deficit = used + spacing + width - available
            if deficit > 0 and deficit > self._room_to_shrink(current):
                lines.append(current)
                current = [(item, width)]
                used = width
                continue
            current.append((item, width))
            used += spacing + width
        if current:
            lines.append(current)
        return lines

    def _arrange(self, rect: QRect, dry_run: bool) -> int:
        margins = self.contentsMargins()
        left = rect.x() + margins.left()
        available = rect.width() - margins.left() - margins.right()
        top = rect.y() + margins.top()
        if available <= 0 or not self._items:
            return rect.height()
        spacing = max(SPACING_FLOOR, self.spacing())

        y = top
        for line in self._lines(available):
            heights = [max(item.sizeHint().height(), item.minimumSize().height()) for item, _ in line]
            reserves = [self._valign_of(item)[1] for item, _ in line]
            # La réserve du bas fait la hauteur de ligne : un item sans réserve atteint le bas
            # de la ligne pendant que les autres restent en retrait.
            line_height = max((h + r for h, r in zip(heights, reserves, strict=True)), default=0)
            self._resize_line(line, available, spacing)
            x = left
            for (item, width), height, reserve in zip(line, heights, reserves, strict=True):
                align, _ = self._valign_of(item)
                if align & Qt.AlignmentFlag.AlignBottom:
                    offset = line_height - reserve - height
                else:
                    offset = (line_height - height) // 2
                if not dry_run:
                    item.setGeometry(QRect(x, y + offset, width, height))
                x += width + spacing
            y += line_height + spacing
        return y - spacing - top + margins.top() + margins.bottom()

    def _resize_line(self, line: list[tuple[QLayoutItem, int]], available: int, spacing: int) -> None:
        """Étire ou rétrécit les items Expanding pour remplir exactement la largeur de la ligne."""
        used = sum(width for _, width in line) + spacing * max(0, len(line) - 1)
        slack = available - used
        stretchable = [index for index, (item, _) in enumerate(line) if _expands(item)]
        if slack == 0 or not stretchable:
            return
        if slack > 0:
            self._share_slack(line, stretchable, slack)
            return
        deficit = -slack
        if deficit > self._room_to_shrink(line):
            return
        share = deficit // len(stretchable)
        rest = deficit - share * len(stretchable)
        for position, index in enumerate(stretchable):
            item, width = line[index]
            floor = item.minimumSize().width()
            take = min(width - floor, share + (1 if position < rest else 0))
            line[index] = (item, width - take)

    def _share_slack(self, line: list[tuple[QLayoutItem, int]], stretchable: list[int], slack: int) -> None:
        """Répartit le surplus au prorata du poids.

        Un stretch de centrage a un poids lourd : deux stretchs de même poids se partagent la
        place restante à parts égales, et le groupe qu'ils encadrent reste centré même si un
        champ Expanding de la même ligne réclame aussi sa part.
        """
        weights = [max(DEFAULT_WEIGHT, self._weights.get(line[index][0], DEFAULT_WEIGHT)) for index in stretchable]
        total = sum(weights)
        given = 0
        for weight, index in zip(weights, stretchable, strict=True):
            share = slack * weight // total
            item, width = line[index]
            line[index] = (item, width + share)
            given += share
        extra = slack - given
        if extra > 0:
            # Le reliquat de la division entière tourne entre les items les plus lourds :
            # deux stretchs de même poids ne diffèrent jamais que d'un pixel.
            heaviest = [position for position, weight in enumerate(weights) if weight == max(weights)]
            for offset in range(extra):
                index = stretchable[heaviest[offset % len(heaviest)]]
                item, width = line[index]
                line[index] = (item, width + 1)


def apply_flow_height(widget: QWidget) -> None:
    """Donne au conteneur d'un `FlowLayout` la hauteur que sa largeur actuelle exige.

    Une `QScrollArea` ne demande jamais height-for-width : sans ce rappel, un bandeau
    qui replie ses lignes sur deux rangées rogne la seconde et ses boutons.
    """
    layout = widget.layout()
    if not isinstance(layout, FlowLayout):
        return
    width = widget.width()
    if width <= 0:
        return
    wanted = layout.heightForWidth(width)
    if wanted > 0 and widget.minimumHeight() != wanted:
        widget.setMinimumHeight(wanted)
