"""Gère le calendrier mensuel : génération, stabilité, remplacement des films.

Fait le lien entre db.py (persistance) et recommender.py (scoring) pour
reproduire le parcours utilisateur qu'on avait défini au départ.
"""
from __future__ import annotations

import json
from datetime import date

from . import db, recommender

SEMAINES_PAR_MOIS = 4


def current_month() -> str:
    return date.today().strftime("%Y-%m")


def ensure_current_calendar(user_id: int) -> dict:
    """Point d'entrée appelé à chaque affichage du programme.

    Si aucun calendrier n'existe encore pour le mois courant, archive
    l'ancien et en génère un nouveau. Sinon ne touche à rien (le calendrier
    doit rester stable tant qu'on est dans le même mois) : c'est ce test
    "existe déjà ?" qui évite de régénérer 4 nouveaux films à chaque fois
    que l'utilisateur ouvre l'app."""
    month = current_month()
    if db.get_calendar(user_id, month) is None:
        _generate_calendar(user_id, month)
    return get_monthly_calendar(user_id, month)


def get_monthly_calendar(user_id: int, month: str | None = None) -> dict | None:
    """Reconstruit le programme affichable pour un mois donné, à partir des
    lignes brutes stockées en base."""
    month = month or current_month()
    calendar = db.get_calendar(user_id, month)
    if calendar is None:
        return None

    # Un « déjà vu »/« pas intéressé » insère une nouvelle ligne pour la même
    # semaine plutôt que d'écraser l'ancienne (conservée pour l'historique) :
    # on ne garde ici que la ligne la plus récente par semaine (id le plus
    # grand = insérée en dernier).
    derniere_par_semaine: dict[int, object] = {}
    for rec in db.get_calendar_recommendations(calendar["id"]):
        courante = derniere_par_semaine.get(rec["week"])
        if courante is None or rec["id"] > courante["id"]:
            derniere_par_semaine[rec["week"]] = rec

    recommandations = []
    for semaine in sorted(derniere_par_semaine):
        rec = derniere_par_semaine[semaine]
        movie = recommender.get_movie(rec["movie_id"]) or {}
        recommandations.append(
            {
                **movie,
                "recommendation_id": rec["id"],
                "week": rec["week"],
                "status": rec["status"],
            }
        )

    return {
        "calendar_id": calendar["id"],
        "month": calendar["month"],
        "status": calendar["status"],
        "recommendations": recommandations,
    }


def get_archived_calendars(user_id: int) -> list[dict]:
    resultats = []
    for calendar in db.get_archived_calendars(user_id):
        resultats.append(get_monthly_calendar(user_id, calendar["month"]))
    return resultats


def _generate_calendar(user_id: int, month: str) -> int:
    """Construit le programme du mois : profil -> exclusions -> 4 meilleurs
    films -> sauvegarde en base."""
    reference_ids = db.get_reference_movies(user_id)
    if not reference_ids:
        raise ValueError(
            "Choisissez au moins un film de référence avant de générer votre programme."
        )

    profile = recommender.build_profile(reference_ids)
    if profile is None:
        raise ValueError("Vos films de référence sont introuvables dans le catalogue.")

    db.archive_active_calendars(user_id)

    # si on ne trouve pas assez de films avec les contraintes fortes, on élargit
    # la recherche petit à petit, mais on garde toujours l'exclusion des films
    # déjà vus ou refusés (ça, c'est non négociable) :
    #   1) exclusion complète + diversité par réalisateur
    #   2) on retire la contrainte "pas recommandé récemment"
    #   3) en dernier recours, on retire aussi la diversité par réalisateur
    exclusion_absolue = db.get_excluded_movie_ids(user_id)
    exclusion_stricte = exclusion_absolue | db.get_recently_recommended_movie_ids(user_id)

    picks = recommender.recommend(profile, exclusion_stricte, k=SEMAINES_PAR_MOIS, diversify=True)
    if len(picks) < SEMAINES_PAR_MOIS:
        picks = recommender.recommend(profile, exclusion_absolue, k=SEMAINES_PAR_MOIS, diversify=True)
    if len(picks) < SEMAINES_PAR_MOIS:
        picks = recommender.recommend(profile, exclusion_absolue, k=SEMAINES_PAR_MOIS, diversify=False)

    calendar_id = db.create_calendar(user_id, month, reference_ids)
    for semaine, film in enumerate(picks, start=1):
        db.add_recommendation(calendar_id, film["movie_id"], semaine)
    return calendar_id


def _replace_recommendation(user_id: int, old_rec) -> dict | None:
    """Trouve un film de remplacement pour la même semaine qu'une
    recommandation qu'on vient d'écarter (déjà vu / pas intéressé).

    On recalcule le profil à partir de l'instantané de références stocké
    sur CE calendrier (calendar["reference_movie_ids"]), pas des références
    actuelles de l'utilisateur — pour rester cohérent avec le reste du
    calendrier même si l'utilisateur a changé ses goûts entre-temps."""
    calendar = db.get_calendar_by_id(old_rec["calendar_id"])
    reference_ids = json.loads(calendar["reference_movie_ids"])
    profile = recommender.build_profile(reference_ids)
    if profile is None:
        return None

    calendar_recs = db.get_calendar_recommendations(calendar["id"])
    current_movie_ids = {r["movie_id"] for r in calendar_recs}
    # on récupère les réalisateurs déjà présents dans les AUTRES semaines du
    # calendrier, pour ne pas proposer un remplaçant du même réalisateur
    avoid_directors = set()
    for r in calendar_recs:
        if r["id"] == old_rec["id"]:
            continue
        info = recommender.get_movie(r["movie_id"])
        if info and info["realisateur"]:
            avoid_directors.add(info["realisateur"])

    exclusion_stricte = (
        db.get_excluded_movie_ids(user_id)
        | db.get_recently_recommended_movie_ids(user_id)
        | current_movie_ids
    )
    picks = recommender.recommend(
        profile, exclusion_stricte, k=1, diversify=True, avoid_directors=avoid_directors
    )

    if not picks:
        # élargissement, même logique que dans _generate_calendar
        exclusion_minimale = db.get_excluded_movie_ids(user_id) | current_movie_ids
        picks = recommender.recommend(profile, exclusion_minimale, k=1, diversify=False)

    if not picks:
        return None

    nouveau_film = picks[0]
    db.add_recommendation(calendar["id"], nouveau_film["movie_id"], old_rec["week"])
    return nouveau_film


def renew_calendar_with_new_references(user_id: int) -> dict | None:
    """Après modification des films de référence : renouvelle toutes les
    semaines du calendrier en cours à partir du nouveau profil, sauf celles
    déjà marquées « regardé après la recommandation », qui ne bougent pas."""
    calendar = db.get_active_calendar(user_id)
    if calendar is None:
        return None

    reference_ids = db.get_reference_movies(user_id)
    profile = recommender.build_profile(reference_ids)
    if profile is None:
        return None

    # on met à jour l'instantané stocké sur le calendrier, pour que les
    # remplacements futurs (déjà vu / pas intéressé) se basent eux aussi sur
    # ce nouveau profil plutôt que sur l'ancien
    db.update_calendar_references(calendar["id"], reference_ids)

    cartes = get_monthly_calendar(user_id, calendar["month"])["recommendations"]
    conservees = [c for c in cartes if c["status"] == "watched"]
    a_renouveler = [c for c in cartes if c["status"] != "watched"]

    exclusion_de_base = db.get_excluded_movie_ids(user_id) | db.get_recently_recommended_movie_ids(user_id)
    # on part des films/réalisateurs déjà conservés (semaines "watched"),
    # puis on les enrichit au fur et à mesure qu'on choisit les remplaçants,
    # pour ne jamais proposer deux fois le même film ou le même réalisateur
    # sur deux semaines du même calendrier
    movie_ids_retenus = {c["movie_id"] for c in conservees}
    directors_retenus = {c["realisateur"] for c in conservees if c["realisateur"]}

    for carte in a_renouveler:
        picks = recommender.recommend(
            profile,
            exclusion_de_base | movie_ids_retenus,
            k=1,
            diversify=True,
            avoid_directors=directors_retenus,
        )
        if not picks:
            exclusion_minimale = db.get_excluded_movie_ids(user_id) | movie_ids_retenus
            picks = recommender.recommend(profile, exclusion_minimale, k=1, diversify=False)
        if not picks:
            continue  # aucun autre candidat dispo, on garde la recommandation actuelle pour cette semaine

        if carte["status"] == "scheduled":
            # la carte n'avait jamais été traitée par l'utilisateur : on
            # marque juste l'ancienne ligne comme remplacée, sans créer
            # d'entrée dans l'historique (contrairement à déjà-vu/refusé)
            db.update_recommendation_status(carte["recommendation_id"], "replaced")

        nouveau_film = picks[0]
        db.add_recommendation(calendar["id"], nouveau_film["movie_id"], carte["week"])
        movie_ids_retenus.add(nouveau_film["movie_id"])
        if nouveau_film["realisateur"]:
            directors_retenus.add(nouveau_film["realisateur"])

    return get_monthly_calendar(user_id, calendar["month"])


def mark_as_already_seen(user_id: int, recommendation_id: int) -> dict | None:
    """« Je l'ai déjà vu » : le film était vu avant d'être recommandé —
    enregistré dans l'historique, remplacé immédiatement sur la même semaine."""
    rec = db.get_recommendation(recommendation_id)
    db.update_recommendation_status(recommendation_id, "already_seen")
    db.record_history(user_id, rec["movie_id"], "already_seen")
    return _replace_recommendation(user_id, rec)


def mark_as_not_interested(user_id: int, recommendation_id: int) -> dict | None:
    """« Pas intéressé » : même mécanique que ci-dessus, avec un statut
    différent (ne sera pas comptabilisé comme "vu" dans l'historique)."""
    rec = db.get_recommendation(recommendation_id)
    db.update_recommendation_status(recommendation_id, "not_interested")
    db.record_history(user_id, rec["movie_id"], "not_interested")
    return _replace_recommendation(user_id, rec)


def mark_as_watched(user_id: int, recommendation_id: int) -> None:
    """« Regardé après la recommandation » : contrairement aux deux
    fonctions précédentes, pas de remplacement — la recommandation a
    rempli son rôle, elle reste affichée avec son badge."""
    rec = db.get_recommendation(recommendation_id)
    db.update_recommendation_status(recommendation_id, "watched")
    db.record_history(user_id, rec["movie_id"], "watched")
