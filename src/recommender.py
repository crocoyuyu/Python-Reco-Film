"""Interface avec le modèle content-based enrichi (notebook 05).

Charge models/modele_content_enrichi.pkl et models/films_content_enrichi.csv
avec des chemins relatifs au projet, et fournit tout ce dont l'app Streamlit
a besoin : recherche de film, liste populaire, construction du profil
utilisateur et calcul des recommandations.

Rappel du principe (voir le notebook 5 pour le détail du calcul) : chaque
film est représenté par un seul vecteur de nombres, obtenu en collant bout à
bout 5 vecteurs TF-IDF pondérés (genres, synopsis, acteurs, réalisateur,
mots-clés). Le profil d'un utilisateur, c'est juste la moyenne des vecteurs
de ses films de référence. Le score d'un film candidat, c'est la similarité
cosinus entre son vecteur et le profil.
"""
from __future__ import annotations

# ast : pour relire les listes d'acteurs/mots-clés stockées comme du texte
# dans le CSV (ex: la chaîne "['Tom Hanks', 'Tim Allen']" -> une vraie liste)
import ast

# pickle : pour recharger le modèle entraîné (modele_content_enrichi.pkl),
# qui contient la matrice combinée déjà calculée par le notebook 5
import pickle

# re + unicodedata : pour la recherche insensible aux accents/casse/espaces
# et pour repérer le motif "Titre, The" à la fin d'un titre
import re
import unicodedata

# Counter : pour compter combien de films appartiennent à chaque genre, et
# en déduire les genres les plus représentés du catalogue
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

# la fonction qui calcule la similarité cosinus entre deux vecteurs — c'est
# elle qui donne le score final de chaque recommandation
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"

CHEMIN_MODELE = MODELS_DIR / "modele_content_enrichi.pkl"
CHEMIN_CATALOGUE = MODELS_DIR / "films_content_enrichi.csv"
CHEMIN_NOTES = DATA_DIR / "nettoye" / "ratings_clean.csv"
# le synopsis a servi au calcul du score (notebook 5) mais n'a pas été gardé
# dans le catalogue final models/films_content_enrichi.csv — on le relit
# directement dans le fichier source du notebook 4 pour l'afficher
CHEMIN_SYNOPSIS = DATA_DIR / "enrichi" / "films_complet.csv"

SEUIL_VOTES_POPULARITE = 50  # nombre minimum de notes pour la liste "populaires"

# MovieLens stocke les titres avec l'article rejeté à la fin ("Matrix, The",
# parfois suivi d'un titre original entre parenthèses) pour faciliter le tri
# alphabétique. On le remet devant pour l'affichage.
_ARTICLES_CONNUS = ("The", "A", "An", "La", "Les", "Le", "El")
_RE_ARTICLE_FIN = re.compile(r"^(.*), (" + "|".join(_ARTICLES_CONNUS) + r")(\s\(.+\))?$")


def _formater_titre(titre: str) -> str:
    """"Matrix, The" -> "The Matrix". Ne touche pas aux titres qui ne
    correspondent pas au motif (ex: "Paris, Texas" reste inchangé)."""
    match = _RE_ARTICLE_FIN.match(titre)
    if match:
        titre_principal, article, parenthese = match.groups()
        return f"{article} {titre_principal}{parenthese or ''}"
    return titre


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents, espaces multiples réduits — pour une
    recherche qui ne bute pas sur la casse ou les accents."""
    # NFKD décompose les caractères accentués en (lettre + accent séparé),
    # puis on filtre les accents (unicodedata.combining) pour ne garder que
    # la lettre : "é" -> "e"
    texte = unicodedata.normalize("NFKD", str(texte))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower()
    return re.sub(r"\s+", " ", texte).strip()


def _sans_espaces(texte: str) -> str:
    """Comme _normaliser, mais retire aussi tous les espaces. Sert à
    comparer deux textes sans se soucier de la façon dont ils sont "coupés"
    en mots (ex: "the godfather" et "thegodfather" doivent matcher)."""
    return _normaliser(texte).replace(" ", "")


def _parse_liste(valeur) -> list[str]:
    """Les colonnes acteurs/mots_cles du CSV contiennent du texte qui
    ressemble à une liste Python (ex: "['Tom Hanks', 'Tim Allen']"). On la
    reconvertit en vraie liste avec ast.literal_eval (plus sûr qu'un eval()
    classique, qui exécuterait n'importe quel code)."""
    if pd.isna(valeur):
        return []
    try:
        resultat = ast.literal_eval(str(valeur))
        return [str(x) for x in resultat] if isinstance(resultat, list) else []
    except (ValueError, SyntaxError):
        return []


@lru_cache(maxsize=1)
def _load_catalogue() -> pd.DataFrame:
    """Charge le catalogue une seule fois (grâce à lru_cache) et prépare
    toutes les colonnes dont le reste du fichier a besoin, pour ne pas
    refaire ce travail à chaque recherche ou génération de programme."""
    films = pd.read_csv(CHEMIN_CATALOGUE)

    synopsis_source = pd.read_csv(CHEMIN_SYNOPSIS, usecols=["movieId", "synopsis", "synopsis_anglais"])
    films = films.merge(synopsis_source, on="movieId", how="left")
    # une chaîne vide compte comme "pas de synopsis", au même titre qu'une
    # vraie valeur manquante (NaN)
    films.loc[films["synopsis"].fillna("").str.strip() == "", "synopsis"] = pd.NA
    films["synopsis_anglais"] = films["synopsis_anglais"].fillna(False).astype(bool)

    films["acteurs_liste"] = films["acteurs"].apply(_parse_liste)
    films["mots_cles_liste"] = films["mots_cles"].apply(_parse_liste)
    films["genres_liste"] = films["genres"].apply(
        lambda g: g.split("|") if isinstance(g, str) and g else []
    )

    # la position de la ligne dans le CSV correspond exactement à l'index de
    # la ligne dans la matrice du modèle (matrice_combinee) — c'est ce qui
    # permet de faire le lien entre un movieId et son vecteur
    films["position"] = range(len(films))

    films["titre_affichage"] = films["titre"].apply(_formater_titre)
    titre_norm = films["titre_affichage"].apply(_normaliser)
    films["titre_normalise"] = titre_norm
    films["titre_sans_espaces"] = titre_norm.str.replace(" ", "", regex=False)

    realisateur_sans_espaces = films["realisateur"].fillna("").apply(_sans_espaces)
    annee_texte = films["annee"].apply(lambda a: "" if pd.isna(a) else str(int(a)))

    # colonne de recherche : titre + année collés l'un à l'autre (pour que
    # "toystory1995" trouve directement le film), puis réalisateur — le tout
    # sans le moindre espace, pour ignorer la façon dont l'utilisateur
    # découpe sa requête en mots
    films["recherche"] = films["titre_sans_espaces"] + annee_texte + realisateur_sans_espaces

    # Un film sans acteurs/mots-clés, sans réalisateur, ou sans synopsis a un
    # bloc à zéro dans le vecteur combiné : la similarité cosinus ne le
    # pénalise jamais sur cette dimension, ce qui gonfle artificiellement son
    # score (vérifié : les films sans synopsis, 7,5% du catalogue, montent à
    # 42% du top 50 des scores). On exige donc au moins un des deux (acteurs
    # ou mots-clés), ET un réalisateur connu, ET un synopsis.
    a_acteurs_ou_mots_cles = (
        films["acteurs_liste"].apply(len) + films["mots_cles_liste"].apply(len)
    ) > 0
    a_realisateur = films["realisateur"].notna()
    a_synopsis = films["synopsis"].notna()
    films["donnees_suffisantes"] = a_acteurs_ou_mots_cles & a_realisateur & a_synopsis
    return films


@lru_cache(maxsize=1)
def _load_matrice():
    """Recharge la matrice combinée déjà calculée par le notebook 5 (une
    ligne par film, colonnes = genres+synopsis+acteurs+réalisateur+mots-clés
    pondérés et collés bout à bout). On ne recalcule rien ici, on réutilise
    directement le travail fait dans le notebook."""
    with open(CHEMIN_MODELE, "rb") as fichier:
        modele = pickle.load(fichier)
    return modele["matrice_combinee"]


@lru_cache(maxsize=1)
def _position_par_movie_id() -> dict[int, int]:
    """Dictionnaire movieId -> numéro de ligne dans la matrice, pour
    retrouver rapidement le vecteur d'un film à partir de son identifiant."""
    films = _load_catalogue()
    return dict(zip(films["movieId"], films["position"]))


@lru_cache(maxsize=1)
def _scores_popularite() -> pd.DataFrame:
    """Score de popularité façon IMDb (moyenne bayésienne), pour la liste
    « Aidez-moi à choisir ».

    Une simple moyenne des notes favoriserait un film noté une seule fois
    à 5/5 face à un film noté 1000 fois à 4.5/5. La moyenne bayésienne
    "tire" la note d'un film vers la moyenne générale tant qu'il n'a pas
    assez de votes (seuil SEUIL_VOTES_POPULARITE), ce qui évite ce biais."""
    notes = pd.read_csv(CHEMIN_NOTES)
    stats = notes.groupby("movieId")["rating"].agg(["count", "mean"])
    moyenne_globale = notes["rating"].mean()
    m = SEUIL_VOTES_POPULARITE
    stats["score"] = (
        stats["count"] / (stats["count"] + m) * stats["mean"]
        + m / (stats["count"] + m) * moyenne_globale
    )
    return stats


def movie_to_dict(row: pd.Series) -> dict:
    """Convertit une ligne du catalogue (format pandas) en dictionnaire
    simple, plus pratique à manipuler côté app Streamlit."""
    return {
        "movie_id": int(row["movieId"]),
        "titre": row["titre_affichage"],
        "genres": row["genres"].split("|") if row["genres"] else [],
        "annee": None if pd.isna(row["annee"]) else int(row["annee"]),
        "realisateur": None if pd.isna(row["realisateur"]) else row["realisateur"],
        "acteurs": row["acteurs_liste"],
        "mots_cles": row["mots_cles_liste"],
        "synopsis": None if pd.isna(row["synopsis"]) else row["synopsis"],
        "synopsis_anglais": bool(row["synopsis_anglais"]),
    }


def get_movie(movie_id: int) -> dict | None:
    """Récupère les infos d'un film à partir de son movieId."""
    films = _load_catalogue()
    match = films[films["movieId"] == int(movie_id)]
    if match.empty:
        return None
    return movie_to_dict(match.iloc[0])


def search_movies(query: str, limit: int = 20) -> list[dict]:
    """Cherche par titre, par réalisateur ou par année (ex: "toystory1995"),
    insensible à la casse, aux accents et aux espaces — "the godfather" et
    "thegodfather" donnent le même résultat."""
    query_sans_espaces = _sans_espaces(query)
    if not query_sans_espaces:
        return []
    films = _load_catalogue()
    # str.contains sur la colonne "recherche" (titre+année+réalisateur,
    # collés sans espaces) : un simple test "le texte cherché apparaît
    # quelque part", peu importe comment l'utilisateur a placé ses espaces
    mask = films["recherche"].str.contains(query_sans_espaces, regex=False)
    resultats = films[mask].copy()
    resultats["exact"] = resultats["titre_sans_espaces"] == query_sans_espaces
    # les correspondances exactes de titre remontent en premier, puis
    # ordre alphabétique
    resultats = resultats.sort_values(["exact", "titre_affichage"], ascending=[False, True])
    return [movie_to_dict(row) for _, row in resultats.head(limit).iterrows()]


def popular_movies(n: int = 8) -> list[dict]:
    """Les n films les mieux notés (au sens de la moyenne bayésienne
    ci-dessus), pour la liste "Aidez-moi à choisir"."""
    films = _load_catalogue()
    stats = _scores_popularite()
    fusion = films.join(stats, on="movieId").dropna(subset=["score"])
    fusion = fusion.sort_values("score", ascending=False).head(n)
    return [movie_to_dict(row) for _, row in fusion.iterrows()]


@lru_cache(maxsize=1)
def top_genres(n: int = 8) -> list[str]:
    """Les n genres les plus représentés dans le catalogue (par nombre de
    films), pour la section "Top recommandations par genre"."""
    films = _load_catalogue()
    compteur: Counter[str] = Counter()
    for genres in films["genres_liste"]:
        compteur.update(genres)
    return [genre for genre, _ in compteur.most_common(n)]


def top_movies_by_genre(genre: str, n: int = 8) -> list[dict]:
    """Les n films les mieux notés parmi ceux qui appartiennent au genre
    donné — même logique de popularité que popular_movies, restreinte à un
    genre."""
    films = _load_catalogue()
    stats = _scores_popularite()
    dans_le_genre = films[films["genres_liste"].apply(lambda gs: genre in gs)]
    fusion = dans_le_genre.join(stats, on="movieId").dropna(subset=["score"])
    fusion = fusion.sort_values("score", ascending=False).head(n)
    return [movie_to_dict(row) for _, row in fusion.iterrows()]


def build_profile(movie_ids: list[int]) -> np.ndarray | None:
    """Construit le profil de l'utilisateur : la moyenne des vecteurs de ses
    films de référence dans la matrice combinée. C'est ce vecteur moyen qui
    sert ensuite de point de comparaison pour noter tous les autres films."""
    matrice = _load_matrice()
    position = _position_par_movie_id()
    indices = [position[int(m)] for m in movie_ids if int(m) in position]
    if not indices:
        return None
    profil = matrice[indices].mean(axis=0)
    return np.asarray(profil)


def explain_recommendation(movie: dict, reference_movies: list[dict]) -> str:
    """Génère le petit texte « Pourquoi ce film ? » à partir des genres,
    mots-clés et réalisateur en commun avec les films de référence.

    Attention : ce n'est pas le calcul du score lui-même (qui compare des
    vecteurs de plusieurs dizaines de milliers de dimensions et n'est pas
    "expliquable" mot à mot). C'est une explication simplifiée, en
    reformulant en français ce que les deux films ont visiblement en
    commun, pour rester lisible."""
    ref_genres: set[str] = set()
    ref_mots_cles: set[str] = set()
    ref_realisateurs: set[str] = set()
    for ref in reference_movies:
        ref_genres.update(ref["genres"])
        ref_mots_cles.update(ref["mots_cles"])
        if ref["realisateur"]:
            ref_realisateurs.add(ref["realisateur"])

    genres_communs = sorted(set(movie["genres"]) & ref_genres)
    mots_cles_communs = sorted(set(movie["mots_cles"]) & ref_mots_cles)
    meme_realisateur = bool(movie["realisateur"]) and movie["realisateur"] in ref_realisateurs

    morceaux = []
    if meme_realisateur:
        morceaux.append(f"le même réalisateur ({movie['realisateur']})")
    if mots_cles_communs:
        morceaux.append("des thèmes comme " + ", ".join(mots_cles_communs[:2]))
    if genres_communs:
        morceaux.append("les genres " + ", ".join(genres_communs[:2]))

    if not morceaux:
        return "Ce film est proche du profil construit à partir de vos films de référence."
    return "Ce film partage avec vos films de référence " + " et ".join(morceaux) + "."


def recommend(
    profile: np.ndarray,
    exclude_movie_ids: set[int],
    k: int = 4,
    diversify: bool = True,
    avoid_directors: set[str] | None = None,
) -> list[dict]:
    """Retourne jusqu'à k films triés par similarité décroissante, en excluant
    exclude_movie_ids et en évitant (si diversify) plusieurs films du même
    réalisateur, y compris ceux listés dans avoid_directors (utile pour
    remplacer un film sans dupliquer un réalisateur déjà présent ailleurs
    dans le calendrier)."""
    films = _load_catalogue()
    matrice = _load_matrice()

    # cosine_similarity compare le profil (1 vecteur) à toute la matrice
    # (9742 vecteurs) d'un coup, et renvoie un score entre 0 et 1 par film.
    # np.argsort trie les indices du score le plus faible au plus fort,
    # donc [::-1] pour avoir du meilleur score au moins bon.
    scores = cosine_similarity(profile, matrice).ravel()
    ordre = np.argsort(scores)[::-1]

    resultats: list[dict] = []
    realisateurs_retenus: set[str] = set(avoid_directors or ())

    # premier passage : on descend le classement et on garde les meilleurs
    # films qui passent tous les filtres (exclusions + diversité)
    for idx in ordre:
        if len(resultats) >= k:
            break
        row = films.iloc[idx]
        movie_id = int(row["movieId"])
        if movie_id in exclude_movie_ids or not row["donnees_suffisantes"]:
            continue

        realisateur = None if pd.isna(row["realisateur"]) else row["realisateur"]
        if diversify and realisateur and realisateur in realisateurs_retenus:
            continue

        info = movie_to_dict(row)
        info["similarite"] = float(scores[idx])
        resultats.append(info)
        if realisateur:
            realisateurs_retenus.add(realisateur)

    if len(resultats) < k:
        # Élargissement : on relâche la contrainte de diversité par réalisateur
        # plutôt que de laisser une recommandation incomplète.
        deja_retenus = {r["movie_id"] for r in resultats}
        for idx in ordre:
            if len(resultats) >= k:
                break
            row = films.iloc[idx]
            movie_id = int(row["movieId"])
            if (
                movie_id in exclude_movie_ids
                or movie_id in deja_retenus
                or not row["donnees_suffisantes"]
            ):
                continue
            info = movie_to_dict(row)
            info["similarite"] = float(scores[idx])
            resultats.append(info)

    return resultats
