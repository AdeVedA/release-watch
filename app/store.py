"""Persistance de l'état dans data/state.json (écriture atomique + sauvegarde)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from app.i18n import DEFAULT_LANGUAGE, Language, normalize_language, t
from app.models import AppState, Repo, Settings
from app.paths import data_dir

STATE_FILENAME: str = "state.json"
BACKUP_SUFFIX: str = ".bak"
SCHEMA_VERSION: int = 4


class StateError(RuntimeError):
    """`state.json` absent, invalide ou non écrivable."""


class StateStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    @classmethod
    def default(cls) -> StateStore:
        """`data/state.json` a cote de l'executable, donc hors du paquet quand il est gele."""
        return cls(data_dir() / STATE_FILENAME)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def folder(self) -> Path:
        return self._path.parent

    def exists(self) -> bool:
        return self._path.is_file()

    def peek_language(self) -> Language:
        """Langue demandée par `state.json`, lue AVANT toute construction d'interface.

        Ne lève jamais : un fichier illisible sera signalé plus tard par `load()`,
        mais l'écran d'erreur doit déjà s'afficher dans une langue.
        """
        if not self._path.is_file():
            return DEFAULT_LANGUAGE
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return DEFAULT_LANGUAGE
        if not isinstance(raw, dict):
            return DEFAULT_LANGUAGE
        settings = raw.get("settings")
        if not isinstance(settings, dict):
            return DEFAULT_LANGUAGE
        return normalize_language(settings.get("language", DEFAULT_LANGUAGE))

    def load(self) -> AppState:
        if not self._path.is_file():
            return AppState()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateError(t("{path} : JSON invalide ({exc})").format(path=self._path, exc=exc)) from exc
        except OSError as exc:
            raise StateError(t("Impossible de lire {path} : {exc}").format(path=self._path, exc=exc)) from exc
        if not isinstance(raw, dict):
            raise StateError(
                t("{path} : racine JSON attendue, obtenu {found}").format(path=self._path, found=type(raw).__name__)
            )
        settings_raw = raw.get("settings", {})
        repos_raw = raw.get("repos", [])
        settings = Settings.from_dict(dict(settings_raw))
        repos: list[Repo] = [Repo.from_dict(dict(item)) for item in list(repos_raw)]
        return AppState(settings=settings, repos=repos)

    def save(self, state: AppState) -> None:
        for repo in state.repos:
            cap = repo.storage_cap()
            if len(repo.releases) > cap:
                repo.releases = repo.releases[:cap]
        payload = {
            "schema": SCHEMA_VERSION,
            "settings": asdict(state.settings),
            "repos": [repo.to_dict() for repo in state.repos],
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            if self._path.is_file():
                os.replace(self._path, self._path.with_name(self._path.name + BACKUP_SUFFIX))
            os.replace(temp, self._path)
        except OSError as exc:
            raise StateError(t("Impossible d'écrire {path} : {exc}").format(path=self._path, exc=exc)) from exc
