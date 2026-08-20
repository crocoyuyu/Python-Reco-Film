"""Tests du parcours utilisateur : création de profil, sélection des films
de référence, génération et stabilité du calendrier, remplacement immédiat
d'une recommandation, historique et renouvellement mensuel.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import calendar_engine as ce
from src import db, posters, recommender

TOY_STORY = 1
TOY_STORY_2 = 3114


@pytest.fixture(autouse=True)
def base_isolee(tmp_path, monkeypatch):
    """Chaque test utilise sa propre base SQLite, isolée de l'application."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db()
    yield


def creer_utilisateur(username="camille"):
    return db.create_user(username, "motdepasse123")


# ---------------------------------------------------------------------------
# Profils
# ---------------------------------------------------------------------------

def test_creation_profil():
    user_id = creer_utilisateur()
    assert db.get_user(user_id)["username"] == "camille"


def test_pseudonyme_deja_utilise_refuse():
    creer_utilisateur("camille")
    with pytest.raises(ValueError):
        creer_utilisateur("camille")


def test_pseudonyme_ou_mdp_vide_refuse():
    with pytest.raises(ValueError):
        db.create_user("", "motdepasse123")
    with pytest.raises(ValueError):
        db.create_user("camille", "")


def test_authentification():
    creer_utilisateur()
    assert db.authenticate_user("camille", "motdepasse123") is not None
    assert db.authenticate_user("camille", "mauvais_mdp") is None


# ---------------------------------------------------------------------------
# Recherche et sélection des films de référence
# ---------------------------------------------------------------------------

def test_recherche_de_film():
    resultats = recommender.search_movies("Toy Story")
    assert any(m["movie_id"] == TOY_STORY for m in resultats)


def test_liste_populaire_disponible():
    assert len(recommender.popular_movies(8)) == 8


def test_selection_dedoublonne_les_films():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY, TOY_STORY, TOY_STORY_2])
    assert db.get_reference_movies(user_id) == [TOY_STORY, TOY_STORY_2]


def test_selection_minimum_un_film():
    user_id = creer_utilisateur()
    with pytest.raises(ValueError):
        db.save_reference_movies(user_id, [])


def test_selection_maximum_quatre_films():
    user_id = creer_utilisateur()
    with pytest.raises(ValueError):
        db.save_reference_movies(user_id, [1, 2, 3, 4, 5])


# ---------------------------------------------------------------------------
# Génération et stabilité du calendrier mensuel
# ---------------------------------------------------------------------------

def test_generation_quatre_recommandations_distinctes_et_hors_references():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar = ce.ensure_current_calendar(user_id)

    movie_ids = [r["movie_id"] for r in calendar["recommendations"]]
    assert len(calendar["recommendations"]) == 4
    assert len(set(movie_ids)) == 4
    assert TOY_STORY not in movie_ids


def test_recommandations_ont_toujours_un_synopsis():
    # non-régression : les films sans synopsis avaient un score gonflé et
    # remontaient trop souvent dans les recommandations (cf. le même bug
    # déjà corrigé pour acteurs/mots-clés/réalisateur)
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar = ce.ensure_current_calendar(user_id)

    for rec in calendar["recommendations"]:
        assert rec["synopsis"], f"{rec['titre']} n'a pas de synopsis"


def test_calendrier_stable_pendant_le_mois():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    premier_appel = ce.ensure_current_calendar(user_id)
    second_appel = ce.ensure_current_calendar(user_id)

    ids_premier = [r["recommendation_id"] for r in premier_appel["recommendations"]]
    ids_second = [r["recommendation_id"] for r in second_appel["recommendations"]]
    assert ids_premier == ids_second


def test_generation_sans_film_de_reference_refusee():
    user_id = creer_utilisateur()
    with pytest.raises(ValueError):
        ce.ensure_current_calendar(user_id)


# ---------------------------------------------------------------------------
# Actions sur une recommandation
# ---------------------------------------------------------------------------

def test_deja_vu_enregistre_et_remplace_immediatement():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar = ce.ensure_current_calendar(user_id)
    premiere_semaine = calendar["recommendations"][0]

    nouveau_film = ce.mark_as_already_seen(user_id, premiere_semaine["recommendation_id"])
    assert nouveau_film is not None

    calendar_maj = ce.get_monthly_calendar(user_id)
    carte_semaine_1 = next(r for r in calendar_maj["recommendations"] if r["week"] == 1)
    assert carte_semaine_1["movie_id"] == nouveau_film["movie_id"]
    assert carte_semaine_1["movie_id"] != premiere_semaine["movie_id"]

    historique = [dict(h) for h in db.get_user_history(user_id)]
    assert any(h["movie_id"] == premiere_semaine["movie_id"] and h["status"] == "already_seen" for h in historique)


def test_pas_interesse_enregistre_et_remplace_immediatement():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar = ce.ensure_current_calendar(user_id)
    premiere_semaine = calendar["recommendations"][0]

    ce.mark_as_not_interested(user_id, premiere_semaine["recommendation_id"])

    rec_originale = db.get_recommendation(premiere_semaine["recommendation_id"])
    assert rec_originale["status"] == "not_interested"

    calendar_maj = ce.get_monthly_calendar(user_id)
    assert len(calendar_maj["recommendations"]) == 4  # une seule carte par semaine, malgré le remplacement


def test_regarde_conserve_sans_remplacement():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar = ce.ensure_current_calendar(user_id)
    premiere_semaine = calendar["recommendations"][0]

    ce.mark_as_watched(user_id, premiere_semaine["recommendation_id"])

    calendar_maj = ce.get_monthly_calendar(user_id)
    carte = next(r for r in calendar_maj["recommendations"] if r["week"] == 1)
    assert carte["status"] == "watched"
    assert carte["movie_id"] == premiere_semaine["movie_id"]  # pas de remplacement


def test_historique_persiste_apres_fermeture_application():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar = ce.ensure_current_calendar(user_id)
    ce.mark_as_watched(user_id, calendar["recommendations"][0]["recommendation_id"])

    # Simule une réouverture de l'application (nouvelle requête sur la même base).
    historique = db.get_user_history(user_id)
    assert len(historique) == 1
    assert historique[0]["status"] == "watched"


# ---------------------------------------------------------------------------
# Renouvellement mensuel
# ---------------------------------------------------------------------------

def test_renouvellement_archive_et_exclut_films_deja_vus_et_refuses():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar_juillet = ce.ensure_current_calendar(user_id)

    deja_vu = calendar_juillet["recommendations"][0]
    refuse = calendar_juillet["recommendations"][1]
    ce.mark_as_already_seen(user_id, deja_vu["recommendation_id"])
    ce.mark_as_not_interested(user_id, refuse["recommendation_id"])

    # On force artificiellement l'ancien calendrier sur un mois passé pour
    # simuler l'ouverture de l'application le mois suivant.
    with db.get_connection() as conn:
        conn.execute("UPDATE calendars SET month = '2025-01' WHERE user_id = ?", (user_id,))

    calendar_aout = ce.ensure_current_calendar(user_id)

    archives = db.get_archived_calendars(user_id)
    assert len(archives) == 1
    assert archives[0]["month"] == "2025-01"

    movie_ids_aout = {r["movie_id"] for r in calendar_aout["recommendations"]}
    assert deja_vu["movie_id"] not in movie_ids_aout
    assert refuse["movie_id"] not in movie_ids_aout


# ---------------------------------------------------------------------------
# Synopsis
# ---------------------------------------------------------------------------

def test_synopsis_present_pour_un_film_courant():
    movie = recommender.get_movie(TOY_STORY)
    assert movie["synopsis"]
    assert len(movie["synopsis"]) > 20
    assert movie["synopsis_anglais"] is False  # a un vrai synopsis français


def test_synopsis_absent_gere_sans_erreur():
    # un des 8 films sans correspondance TMDB du tout
    movie = recommender.get_movie(791)
    assert movie["synopsis"] is None
    assert movie["synopsis_anglais"] is False


def test_synopsis_de_secours_en_anglais_marque_comme_tel():
    films = recommender._load_catalogue()
    exemple = films[films["synopsis_anglais"]].iloc[0]
    movie = recommender.get_movie(int(exemple["movieId"]))
    assert movie["synopsis"]
    assert movie["synopsis_anglais"] is True


# ---------------------------------------------------------------------------
# Affichage des titres et recherche
# ---------------------------------------------------------------------------

def test_titre_avec_article_rejete_est_remis_devant():
    matrix = recommender.search_movies("Matrix")
    titres = [m["titre"] for m in matrix]
    assert "The Matrix" in titres
    assert not any(t.endswith(", The") for t in titres)


def test_recherche_insensible_accents_casse_espaces():
    resultat_normal = recommender.search_movies("almodovar")
    resultat_accents_majuscules_espaces = recommender.search_movies("  ALMODÓVAR  ")
    assert resultat_normal
    assert resultat_normal == resultat_accents_majuscules_espaces


def test_recherche_par_realisateur():
    resultats = recommender.search_movies("Spielberg")
    assert resultats
    assert all(m["realisateur"] and "spielberg" in m["realisateur"].lower() for m in resultats)


def test_recherche_ignore_les_espaces():
    avec_espaces = recommender.search_movies("the godfather")
    sans_espaces = recommender.search_movies("thegodfather")
    assert avec_espaces
    assert avec_espaces == sans_espaces


def test_recherche_par_titre_et_annee():
    resultats = recommender.search_movies("toystory1995")
    titres = [m["titre"] for m in resultats]
    assert "Toy Story" in titres


def test_top_genres_retourne_les_genres_les_plus_frequents():
    genres = recommender.top_genres(8)
    assert len(genres) == 8
    assert "Drama" in genres  # le genre le plus représenté dans MovieLens


def test_top_movies_by_genre_ne_retourne_que_ce_genre():
    resultats = recommender.top_movies_by_genre("Drama", 8)
    assert len(resultats) == 8
    assert all("Drama" in m["genres"] for m in resultats)


# ---------------------------------------------------------------------------
# Renouvellement après modification des films de référence
# ---------------------------------------------------------------------------

def test_modification_references_renouvelle_tout_sauf_les_films_regardes():
    user_id = creer_utilisateur()
    db.save_reference_movies(user_id, [TOY_STORY])
    calendar = ce.ensure_current_calendar(user_id)

    # la semaine 1 est marquée comme regardée après la recommandation
    semaine_1 = calendar["recommendations"][0]
    ce.mark_as_watched(user_id, semaine_1["recommendation_id"])
    films_avant = {r["week"]: r["movie_id"] for r in ce.get_monthly_calendar(user_id)["recommendations"]}

    # on change complètement les films de référence
    nouveau_film = recommender.search_movies("Godfather")[0]
    db.save_reference_movies(user_id, [nouveau_film["movie_id"]])
    ce.renew_calendar_with_new_references(user_id)

    films_apres = {r["week"]: r["movie_id"] for r in ce.get_monthly_calendar(user_id)["recommendations"]}

    assert films_apres[1] == films_avant[1]  # le film regardé ne bouge pas
    for semaine in (2, 3, 4):
        assert films_apres[semaine] != films_avant[semaine]  # les autres sont renouvelés


# ---------------------------------------------------------------------------
# Affiches (src/posters.py)
# ---------------------------------------------------------------------------

def test_sans_cle_api_aucune_affiche_et_pas_de_plantage(monkeypatch):
    monkeypatch.setattr(posters, "API_KEY", None)
    monkeypatch.setattr(posters, "_cache", {})
    assert posters.get_poster_url(TOY_STORY) is None


@pytest.mark.skipif(not posters.API_KEY, reason="pas de clé TMDB_API_KEY configurée")
def test_avec_cle_api_renvoie_une_url_tmdb():
    url = posters.get_poster_url(TOY_STORY)
    assert url is not None
    assert url.startswith("https://image.tmdb.org/t/p/")


@pytest.mark.skipif(not posters.API_KEY, reason="pas de clé TMDB_API_KEY configurée")
def test_le_cache_evite_un_second_appel_reseau():
    premier_appel = posters.get_poster_url(TOY_STORY)
    # movieId absent du cache -> on force une entrée factice pour vérifier
    # qu'elle est bien relue telle quelle, sans nouvel appel à l'API
    posters._cache["999999"] = "https://image.tmdb.org/t/p/w200/faux.jpg"
    assert posters.get_poster_url(999999) == "https://image.tmdb.org/t/p/w200/faux.jpg"
    assert premier_appel == posters.get_poster_url(TOY_STORY)
