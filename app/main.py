"""App Streamlit : inscription/login, sélection des films de référence,
programme mensuel et espace personnel.

Point important pour comprendre tout le fichier : contrairement à une app
web classique, Streamlit ré-exécute ce fichier ENTIÈREMENT à chaque clic sur
un bouton. Ce qui doit survivre d'un clic à l'autre (l'utilisateur connecté,
la page affichée, la sélection de films en cours...) est donc stocké dans
`st.session_state`, un dictionnaire qui persiste entre les exécutions. Et
`st.rerun()` sert à forcer cette ré-exécution immédiatement après avoir
changé quelque chose dans session_state, pour rafraîchir l'écran tout de
suite plutôt que d'attendre la prochaine interaction.
"""
from __future__ import annotations

import sys
from pathlib import Path

# on ajoute la racine du projet au chemin de recherche des modules Python,
# pour pouvoir faire "from src import ..." même en lançant ce fichier
# directement avec streamlit run (qui ne connaît pas la structure du projet)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src import calendar_engine as ce
from src import db, posters, recommender

MOIS_FR = {
    1: "janvier", 2: "février", 3: "mars", 4: "avril", 5: "mai", 6: "juin",
    7: "juillet", 8: "août", 9: "septembre", 10: "octobre", 11: "novembre", 12: "décembre",
}
LABEL_SEMAINE = {
    1: "Semaine 1 — Du 1er au 7",
    2: "Semaine 2 — Du 8 au 14",
    3: "Semaine 3 — Du 15 au 21",
    4: "Semaine 4 — Du 22 à la fin du mois",
}

db.init_db()  # ne fait rien si les tables existent déjà (CREATE TABLE IF NOT EXISTS)

st.set_page_config(page_title="Mon programme cinéma", page_icon="🎬", layout="centered")


def mois_affiche(month: str) -> str:
    """'2026-08' -> 'août 2026'."""
    annee, mois = month.split("-")
    return f"{MOIS_FR[int(mois)]} {annee}"


def go(page: str) -> None:
    """Change la page affichée. Stocké dans session_state pour survivre à
    la ré-exécution du script déclenchée par le prochain clic — voir le
    routage tout en bas du fichier, qui lit cette valeur pour savoir quel
    écran dessiner."""
    st.session_state.page = page


def selection_state() -> list[int]:
    """La liste des films en cours de sélection (écran "Choisissez vos
    films de référence"). setdefault crée la clé si elle n'existe pas
    encore, sans écraser une sélection déjà commencée."""
    return st.session_state.setdefault("selection_ids", [])


# ---------------------------------------------------------------------------
# Écrans non authentifiés
# ---------------------------------------------------------------------------

def ecran_accueil() -> None:
    st.title("Mon programme cinéma")
    st.write("Découvrez chaque mois quatre films sélectionnés selon vos goûts.")
    col1, col2 = st.columns(2)
    if col1.button("Inscription", use_container_width=True):
        go("inscription")
    if col2.button("Login", use_container_width=True):
        go("login")


def ecran_inscription() -> None:
    st.title("Inscription")
    # st.form regroupe les champs et le bouton : rien n'est envoyé tant que
    # l'utilisateur n'a pas cliqué sur le bouton "submit" du formulaire (par
    # défaut, un text_input seul déclenche une exécution à chaque frappe)
    with st.form("form_inscription"):
        username = st.text_input("Pseudonyme")
        password = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Créer mon profil")

    if submit:
        try:
            user_id = db.create_user(username, password)
        except ValueError as exc:
            st.error(str(exc))
        else:
            _connecter(user_id)

    if st.button("← Retour"):
        go("accueil")


def ecran_login() -> None:
    st.title("Ouvrir un profil existant")
    with st.form("form_login"):
        username = st.text_input("Pseudonyme")
        password = st.text_input("Mot de passe", type="password")
        submit = st.form_submit_button("Se connecter")

    if submit:
        user = db.authenticate_user(username, password)
        if user is None:
            st.error("Pseudonyme ou mot de passe incorrect.")
        else:
            _connecter(user["id"])

    if st.button("← Retour"):
        go("accueil")


def _connecter(user_id: int) -> None:
    """Appelée après une inscription ou un login réussi : décide de l'écran
    suivant selon la situation de l'utilisateur (nouveau -> guide, sans
    référence -> sélection, sinon -> programme direct)."""
    st.session_state.user_id = user_id
    user = db.get_user(user_id)
    refs = db.get_reference_movies(user_id)
    if not refs and user["affichage_guide"]:
        go("guide")
    elif not refs:
        st.session_state.selection_mode = "creation"
        go("selection")
    else:
        go("programme")
    st.rerun()


# ---------------------------------------------------------------------------
# Présentation + sélection des films de référence
# ---------------------------------------------------------------------------

def ecran_guide() -> None:
    st.title("Comment fonctionne l'application ?")
    st.markdown(
        "- Choisissez entre un et quatre films que vous aimez.\n"
        "- Nous analysons leurs genres, thèmes, réalisateurs, acteurs et synopsis.\n"
        "- Vous recevez quatre recommandations pour le mois.\n"
        "- Signalez les films déjà vus ou ceux qui ne vous intéressent pas.\n"
        "- Une nouvelle sélection est créée chaque mois."
    )
    st.caption("Plus vous sélectionnez de films, plus les recommandations seront précises. Un seul film suffit pour commencer.")
    ne_plus_afficher = st.checkbox("Ne plus afficher")
    if st.button("Choisir mes films", type="primary"):
        if ne_plus_afficher:
            db.set_guide_seen(st.session_state.user_id)
        st.session_state.selection_mode = "creation"
        go("selection")
        st.rerun()


def ecran_selection() -> None:
    user_id = st.session_state.user_id
    # deux usages de cet écran : "creation" (premier profil, mène à l'écran
    # de confirmation) et "edition" (modification depuis l'espace
    # personnel, enregistre directement) — mode stocké en session_state par
    # l'écran qui a amené ici (guide, ou bouton "Modifier mes références")
    mode = st.session_state.get("selection_mode", "creation")
    if "selection_ids" not in st.session_state:
        st.session_state.selection_ids = db.get_reference_movies(user_id) if mode == "edition" else []

    selection = selection_state()

    st.title("Choisissez vos films de référence")
    st.caption(f"{len(selection)} film(s) sélectionné(s) sur 4")

    st.subheader("Rechercher un film")
    query = st.text_input(
        "Titre du film",
        key="recherche_film",
        label_visibility="collapsed",
        placeholder="Titre, réalisateur ou année (ex : toystory1995)",
    )
    st.caption("Vous pouvez chercher par titre du film, nom du réalisateur, ou année de sortie.")
    if query:
        resultats = recommender.search_movies(query, limit=10)
        if not resultats:
            st.info("Aucun film correspondant n'a été trouvé dans notre catalogue.")
        for movie in resultats:
            _ligne_film_selectionnable(movie, selection, contexte="recherche")

    with st.expander("Aidez-moi à choisir"):
        st.caption("Films appréciés du public")
        for movie in recommender.popular_movies(8):
            _ligne_film_selectionnable(movie, selection, contexte="populaire")

    with st.expander("Top recommandations par genre"):
        # 8 boutons (4 par ligne) pour les genres les plus représentés dans
        # le catalogue ; cliquer sur un genre mémorise le choix en
        # session_state et affiche en dessous les films les plus populaires
        # de ce genre
        genres_disponibles = recommender.top_genres(8)
        colonnes = st.columns(4)
        for i, genre in enumerate(genres_disponibles):
            if colonnes[i % 4].button(genre, key=f"genre_bouton_{genre}"):
                st.session_state.genre_choisi = genre
                st.rerun()

        genre_choisi = st.session_state.get("genre_choisi")
        if genre_choisi in genres_disponibles:
            st.caption(f"Films populaires en {genre_choisi}")
            for movie in recommender.top_movies_by_genre(genre_choisi, 8):
                _ligne_film_selectionnable(movie, selection, contexte=f"genre_{genre_choisi}")

    st.subheader("Mes films sélectionnés")
    if not selection:
        st.write("Aucun film sélectionné pour l'instant.")
    for movie_id in list(selection):
        movie = recommender.get_movie(movie_id)
        if movie is None:
            continue
        col1, col2 = st.columns([4, 1])
        annee = f" — {movie['annee']}" if movie["annee"] else ""
        col1.write(f"{movie['titre']}{annee}")
        if col2.button("Retirer", key=f"retirer_{movie_id}"):
            selection.remove(movie_id)
            st.rerun()

    st.divider()
    if len(selection) == 0:
        st.button("Sélectionnez au moins un film pour continuer", disabled=True)
    elif mode == "edition":
        if st.button("Enregistrer mes films de référence", type="primary"):
            with st.spinner("Mise à jour de votre programme…"):
                db.save_reference_movies(user_id, selection)
                del st.session_state.selection_ids
                ce.renew_calendar_with_new_references(user_id)
            st.success(
                "Votre programme a été mis à jour avec vos nouveaux films de référence. "
                "Les films déjà regardés grâce à une recommandation ne changent pas."
            )
            go("programme")
            st.rerun()
    else:
        label = "Créer mon programme du mois" if len(selection) == 4 else f"Continuer avec {len(selection)} film(s)"
        if st.button(label, type="primary"):
            go("confirmation")
            st.rerun()

    if mode == "edition" and st.button("← Annuler"):
        del st.session_state.selection_ids
        go("programme")
        st.rerun()


def _ligne_film_selectionnable(movie: dict, selection: list[int], contexte: str) -> None:
    """Affiche un film avec son bouton Ajouter/Ajouté, que ce soit dans les
    résultats de recherche ou dans la liste "Aidez-moi à choisir".

    `contexte` sert uniquement à fabriquer une clé (key=) unique pour
    chaque bouton : Streamlit exige que deux widgets n'aient jamais la même
    clé, or un même film peut apparaître à la fois dans les résultats de
    recherche ET dans la liste populaire — sans ce préfixe, ça provoquerait
    une erreur de clé dupliquée."""
    col_affiche, col1, col2 = st.columns([1, 3, 1])
    poster_url = posters.get_poster_url(movie["movie_id"])
    if poster_url:
        col_affiche.image(poster_url, use_container_width=True)
    annee = f" — {movie['annee']}" if movie["annee"] else ""
    realisateur = f" · {movie['realisateur']}" if movie["realisateur"] else ""
    col1.write(f"**{movie['titre']}**{annee}{realisateur}")
    deja_choisi = movie["movie_id"] in selection
    plein = len(selection) >= 4
    cle = f"ajout_{contexte}_{movie['movie_id']}"
    if deja_choisi:
        col2.button("Ajouté", key=cle, disabled=True)
    elif plein:
        col2.button("Ajouter", key=cle, disabled=True)
    elif col2.button("Ajouter", key=cle):
        selection.append(movie["movie_id"])
        st.rerun()


def ecran_confirmation() -> None:
    """Récapitulatif avant de lancer le calcul du programme (uniquement
    lors de la création du tout premier profil, pas en édition)."""
    user_id = st.session_state.user_id
    selection = selection_state()
    st.title("Vos films de référence")
    for movie_id in selection:
        movie = recommender.get_movie(movie_id)
        if movie:
            annee = f" ({movie['annee']})" if movie["annee"] else ""
            st.write(f"- {movie['titre']}{annee}")

    st.caption(
        "Votre programme sera construit à partir des genres, des thèmes, "
        "des réalisateurs, des acteurs et des synopsis de ces films."
    )

    col1, col2 = st.columns(2)
    if col1.button("Modifier ma sélection"):
        go("selection")
        st.rerun()
    if col2.button("Générer mon programme", type="primary"):
        with st.spinner("Nous préparons votre programme cinéma…"):
            db.save_reference_movies(user_id, selection)
            del st.session_state.selection_ids
            ce.ensure_current_calendar(user_id)
        go("programme")
        st.rerun()


# ---------------------------------------------------------------------------
# Programme mensuel
# ---------------------------------------------------------------------------

def ecran_programme() -> None:
    user_id = st.session_state.user_id
    user = db.get_user(user_id)
    # génère le programme du mois s'il n'existe pas encore, sinon renvoie
    # l'existant tel quel (voir la docstring de ensure_current_calendar)
    calendar = ce.ensure_current_calendar(user_id)

    st.title(f"Votre programme d'{mois_affiche(calendar['month'])}")
    st.caption("Quatre films sélectionnés selon vos goûts, à découvrir à votre rythme.")

    watched = sum(1 for r in calendar["recommendations"] if r["status"] == "watched")
    st.progress(watched / 4, text=f"{watched} film(s) regardé(s) sur 4")

    onglet_programme, onglet_refs, onglet_historique, onglet_archives = st.tabs(
        ["Programme actuel", "Mes films de référence", "Mon historique", "Anciens programmes"]
    )

    with onglet_programme:
        reference_ids = db.get_reference_movies(user_id)
        reference_movies = [recommender.get_movie(m) for m in reference_ids]
        reference_movies = [m for m in reference_movies if m]
        for rec in calendar["recommendations"]:
            _carte_recommandation(user_id, rec, reference_movies)

    with onglet_refs:
        st.subheader("Mes films de référence")
        for movie in reference_movies:
            annee = f" ({movie['annee']})" if movie["annee"] else ""
            st.write(f"- {movie['titre']}{annee}")
        if st.button("Modifier mes films de référence"):
            st.session_state.selection_mode = "edition"
            go("selection")
            st.rerun()

    with onglet_historique:
        st.subheader("Mon historique")
        historique = db.get_user_history(user_id)
        if not historique:
            st.write("Aucun film dans votre historique pour le moment.")
        libelle_statut = {"watched": "Regardé après la recommandation", "already_seen": "Déjà vu auparavant"}
        for entree in historique:
            movie = recommender.get_movie(entree["movie_id"])
            titre = movie["titre"] if movie else f"Film #{entree['movie_id']}"
            st.write(f"**{titre}** — {libelle_statut.get(entree['status'], entree['status'])} ({entree['date']})")

    with onglet_archives:
        st.subheader("Mes anciens programmes")
        archives = ce.get_archived_calendars(user_id)
        if not archives:
            st.write("Aucun programme archivé pour le moment.")
        for ancien in sorted(archives, key=lambda c: c["month"], reverse=True):
            with st.expander(mois_affiche(ancien["month"]).capitalize()):
                for rec in ancien["recommendations"]:
                    annee = f" ({rec['annee']})" if rec.get("annee") else ""
                    st.write(f"- {rec['titre']}{annee} — {rec['status']}")

    st.divider()
    if st.button("Se déconnecter"):
        # on vide juste les clés de session_state utilisées par ce compte :
        # au prochain rerun, "user_id" n'existe plus -> le routage plus bas
        # renvoie automatiquement vers les écrans non-authentifiés
        for cle in ("user_id", "page", "selection_ids", "selection_mode", "genre_choisi"):
            st.session_state.pop(cle, None)
        st.rerun()


def _carte_recommandation(user_id: int, rec: dict, reference_movies: list[dict]) -> None:
    """Affiche la carte d'une recommandation (une semaine du programme) :
    infos du film, explication, fiche optionnelle, puis badge si déjà
    regardé ou boutons d'action sinon."""
    with st.container(border=True):
        st.caption(LABEL_SEMAINE.get(rec["week"], f"Semaine {rec['week']}"))

        col_affiche, col_infos = st.columns([1, 2])
        poster_url = posters.get_poster_url(rec["movie_id"])
        if poster_url:
            col_affiche.image(poster_url, use_container_width=True)
        with col_infos:
            annee = f"{rec['annee']}" if rec.get("annee") else ""
            realisateur = f" — {rec['realisateur']}" if rec.get("realisateur") else ""
            st.subheader(rec["titre"])
            st.write(f"{annee}{realisateur}")
            if rec.get("genres"):
                st.write(", ".join(rec["genres"]))

        st.write("**Pourquoi ce film ?**")
        st.write(recommender.explain_recommendation(rec, reference_movies))

        # la fiche n'est affichée que s'il y a effectivement quelque chose
        # à montrer (certains films n'ont ni synopsis, ni acteurs, ni
        # mots-clés en base)
        if rec.get("synopsis") or rec.get("acteurs") or rec.get("mots_cles"):
            with st.expander("Voir l'information supplémentaire"):
                if rec.get("synopsis"):
                    prefixe = "*(en anglais)* " if rec.get("synopsis_anglais") else ""
                    st.markdown(prefixe + rec["synopsis"])
                if rec.get("acteurs"):
                    st.write("Avec : " + ", ".join(rec["acteurs"]))
                if rec.get("mots_cles"):
                    st.write("Mots-clés : " + ", ".join(rec["mots_cles"][:8]))

        if rec["status"] == "watched":
            st.success("✓ Regardé après la recommandation")
        elif rec["status"] == "scheduled":
            _actions_recommandation(user_id, rec)


LIBELLES_ACTIONS = {
    "deja_vu": "Je l'ai déjà vu",
    "pas_interesse": "Pas intéressé",
    "regarde": "Regardé après la recommandation",
}
LIBELLES_CONFIRMATION = {
    "deja_vu": "Confirmer : vous aviez déjà vu ce film avant qu'il soit recommandé ?",
    "pas_interesse": "Confirmer : ce film ne vous intéresse pas ?",
    "regarde": "Confirmer : vous avez regardé ce film grâce à cette recommandation ?",
}


def _actions_recommandation(user_id: int, rec: dict) -> None:
    """Boutons d'action avec confirmation en deux temps : un premier clic
    ne fait qu'enregistrer l'intention dans session_state (rien n'est écrit
    en base) et affiche un message "Confirmer ?" ; c'est seulement le clic
    sur "Confirmer" qui déclenche réellement l'action. "Annuler" efface
    l'intention et revient aux 3 boutons de départ."""
    cle_attente = f"action_en_attente_{rec['recommendation_id']}"
    action_en_attente = st.session_state.get(cle_attente)

    if action_en_attente is None:
        col1, col2, col3 = st.columns(3)
        if col1.button(LIBELLES_ACTIONS["deja_vu"], key=f"deja_vu_{rec['recommendation_id']}"):
            st.session_state[cle_attente] = "deja_vu"
            st.rerun()
        if col2.button(LIBELLES_ACTIONS["pas_interesse"], key=f"pas_interesse_{rec['recommendation_id']}"):
            st.session_state[cle_attente] = "pas_interesse"
            st.rerun()
        if col3.button(LIBELLES_ACTIONS["regarde"], key=f"regarde_{rec['recommendation_id']}"):
            st.session_state[cle_attente] = "regarde"
            st.rerun()
        return

    st.warning(LIBELLES_CONFIRMATION[action_en_attente])
    col1, col2 = st.columns(2)
    if col1.button("Confirmer", key=f"confirmer_{rec['recommendation_id']}", type="primary"):
        # c'est seulement ici, au moment de la confirmation, qu'on appelle
        # calendar_engine (écriture en base + remplacement éventuel)
        if action_en_attente == "deja_vu":
            ce.mark_as_already_seen(user_id, rec["recommendation_id"])
        elif action_en_attente == "pas_interesse":
            ce.mark_as_not_interested(user_id, rec["recommendation_id"])
        else:
            ce.mark_as_watched(user_id, rec["recommendation_id"])
        del st.session_state[cle_attente]
        st.rerun()
    if col2.button("Annuler", key=f"annuler_{rec['recommendation_id']}"):
        del st.session_state[cle_attente]
        st.rerun()


# ---------------------------------------------------------------------------
# Routage
# ---------------------------------------------------------------------------

# ce bloc s'exécute à CHAQUE rerun du script (donc à chaque clic sur un
# bouton, dans n'importe quel écran) : il regarde si un utilisateur est
# connecté (présence de "user_id" en session_state) puis lit "page" pour
# savoir quelle fonction d'écran appeler. .get(page, ecran_par_defaut) : si
# la valeur de "page" ne correspond à aucun écran connu, on retombe sur un
# écran par défaut plutôt que de planter.
if "user_id" not in st.session_state:
    page = st.session_state.get("page", "accueil")
    {
        "accueil": ecran_accueil,
        "inscription": ecran_inscription,
        "login": ecran_login,
    }.get(page, ecran_accueil)()
else:
    page = st.session_state.get("page", "programme")
    {
        "guide": ecran_guide,
        "selection": ecran_selection,
        "confirmation": ecran_confirmation,
        "programme": ecran_programme,
    }.get(page, ecran_programme)()
