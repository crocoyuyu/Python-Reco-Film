"""Récupère et met en cache les affiches de films via l'API TMDB.

Optionnel par conception : si aucune clé API n'est configurée (variable
TMDB_API_KEY dans le fichier .env), ou en cas d'erreur réseau, get_poster_url
renvoie simplement None et l'app n'affiche pas d'affiche pour ce film, sans
jamais planter.

Fonctionnement : au premier affichage d'un film, on appelle l'API TMDB pour
récupérer son poster_path (le même type d'appel que le notebook 4, mais un
seul film à la fois, à la demande) et on le sauvegarde dans un petit fichier
JSON local (models/posters_cache.json). Les affichages suivants du même film
relisent directement ce cache, sans nouvel appel réseau.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

CHEMIN_LINKS = ROOT / "data" / "nettoye" / "links_clean.csv"
CHEMIN_CACHE = ROOT / "models" / "posters_cache.json"
TAILLE_IMAGE = "w200"  # format TMDB, largement suffisant pour une carte de film

API_KEY = os.environ.get("TMDB_API_KEY")

_cache: dict[str, str | None] | None = None
_tmdb_id_par_movie_id: dict[int, int] | None = None


def _charger_cache() -> dict[str, str | None]:
    global _cache
    if _cache is None:
        if CHEMIN_CACHE.exists():
            with open(CHEMIN_CACHE, encoding="utf-8") as fichier:
                _cache = json.load(fichier)
        else:
            _cache = {}
    return _cache


def _sauvegarder_cache() -> None:
    CHEMIN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(CHEMIN_CACHE, "w", encoding="utf-8") as fichier:
        json.dump(_cache, fichier)


def _tmdb_id(movie_id: int) -> int | None:
    """movieId (MovieLens) -> tmdbId (TMDB), via links_clean.csv. Certains
    films n'ont pas de correspondance TMDB (8 sur 9742) : on renvoie None."""
    global _tmdb_id_par_movie_id
    if _tmdb_id_par_movie_id is None:
        links = pd.read_csv(CHEMIN_LINKS)
        _tmdb_id_par_movie_id = dict(zip(links["movieId"], links["tmdbId"]))
    tmdb_id = _tmdb_id_par_movie_id.get(movie_id)
    if tmdb_id is None or pd.isna(tmdb_id):
        return None
    return int(tmdb_id)


def get_poster_url(movie_id: int) -> str | None:
    """URL de l'affiche d'un film, ou None si indisponible (pas de clé API
    configurée, film sans correspondance TMDB, ou film sans affiche)."""
    cache = _charger_cache()
    cle = str(movie_id)
    if cle in cache:
        return cache[cle]

    if not API_KEY:
        return None

    tmdb_id = _tmdb_id(movie_id)
    if tmdb_id is None:
        cache[cle] = None
        _sauvegarder_cache()
        return None

    try:
        reponse = requests.get(
            f"https://api.themoviedb.org/3/movie/{tmdb_id}",
            params={"api_key": API_KEY},
            timeout=5,
        )
        reponse.raise_for_status()
        poster_path = reponse.json().get("poster_path")
    except requests.RequestException:
        # erreur réseau : on ne met rien en cache, pour réessayer la
        # prochaine fois plutôt que de figer une absence d'affiche
        return None

    url = f"https://image.tmdb.org/t/p/{TAILLE_IMAGE}{poster_path}" if poster_path else None
    cache[cle] = url
    _sauvegarder_cache()
    return url
