"""Accès SQLite pour les profils, films de référence, calendriers et historique.

Reprend le schéma qu'on avait esquissé dans table.sql, avec un hash du mot
de passe au lieu de le stocker en clair.
"""
from __future__ import annotations

# hashlib + secrets : pour ne jamais stocker un mot de passe en clair dans
# la base. hashlib calcule le hash, secrets génère le "sel" aléatoire (voir
# _hash_password ci-dessous)
import hashlib
import secrets

# json : pour sauvegarder une liste Python (les films de référence utilisés
# pour générer un calendrier) dans une simple colonne texte SQLite
import json

# sqlite3 : la base de données elle-même — un simple fichier .db sur le
# disque, pas besoin d'installer un serveur de base de données à part
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"

# les statuts possibles pour une recommandation dans le calendrier, et pour
# une entrée de l'historique — sert juste à valider les valeurs en entrée
# des fonctions plus bas (éviter une faute de frappe du style "wached")
STATUTS_RECOMMANDATION = {
    "scheduled",
    "watched",
    "already_seen",
    "not_interested",
    "replaced",
}
STATUTS_HISTORIQUE = {"favorite", "watched", "already_seen", "not_interested"}


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Transforme un mot de passe en une empreinte impossible à inverser.

    Le "sel" (salt) est une valeur aléatoire différente pour chaque
    utilisateur : sans lui, deux utilisateurs avec le même mot de passe
    auraient exactement le même hash en base, ce qui faciliterait une
    attaque. pbkdf2_hmac répète le calcul de hash 100 000 fois (le paramètre
    100_000) pour rendre une attaque par force brute beaucoup plus lente."""
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000)
    return digest.hex(), salt


@contextmanager
def get_connection():
    """Ouvre une connexion à la base, la passe à qui l'utilise (yield), puis
    valide les changements (commit) et ferme proprement — même en cas
    d'erreur, grâce au bloc finally. Toutes les fonctions du fichier
    utilisent `with get_connection() as conn:` pour ne jamais oublier de
    fermer une connexion."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # row_factory permet d'accéder aux colonnes par leur nom (row["titre"])
    # plutôt que par leur position (row[2]), beaucoup plus lisible
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Crée les 5 tables si elles n'existent pas encore (IF NOT EXISTS =
    ne fait rien si elles sont déjà là). Appelée une fois au démarrage de
    l'app Streamlit."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                affichage_guide INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS reference_movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                movie_id INTEGER NOT NULL,
                date_added TEXT NOT NULL,
                UNIQUE(user_id, movie_id)
            );

            CREATE TABLE IF NOT EXISTS calendars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                month TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                reference_movie_ids TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, month)
            );

            CREATE TABLE IF NOT EXISTS recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                calendar_id INTEGER NOT NULL REFERENCES calendars(id),
                movie_id INTEGER NOT NULL,
                week INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                rating_feedback TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                movie_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                date TEXT NOT NULL
            );
            """
        )


# ---------------------------------------------------------------------------
# Profils
# ---------------------------------------------------------------------------

def create_user(username: str, password: str) -> int:
    """Crée un compte. Lève une ValueError si le pseudo/mdp est vide, ou si
    le pseudo est déjà pris (contrainte UNIQUE sur la colonne username, qui
    fait échouer l'INSERT avec une IntegrityError qu'on transforme en
    message compréhensible)."""
    username = username.strip()
    if not username or not password:
        raise ValueError("Le pseudonyme et le mot de passe ne doivent pas être vides.")

    password_hash, salt = _hash_password(password)
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO users (username, password_hash, password_salt, created_at) "
                "VALUES (?, ?, ?, ?)",
                (username, password_hash, salt, date.today().isoformat()),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("Ce pseudonyme est déjà utilisé.") from exc
        return cursor.lastrowid


def authenticate_user(username: str, password: str) -> sqlite3.Row | None:
    """Vérifie le pseudo/mot de passe. On recalcule le hash du mot de passe
    fourni avec le même sel que celui stocké, puis on compare les deux hash
    (jamais les mots de passe en clair). secrets.compare_digest plutôt qu'un
    simple == : évite qu'un attaquant devine le mot de passe petit à petit
    en mesurant le temps de réponse (timing attack)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
    if row is None:
        return None
    expected_hash, _ = _hash_password(password, row["password_salt"])
    if not secrets.compare_digest(expected_hash, row["password_hash"]):
        return None
    return row


def get_user(user_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def set_guide_seen(user_id: int) -> None:
    """Coche "affichage_guide" à 0 quand l'utilisateur choisit "Ne plus
    afficher" sur l'écran de présentation, pour ne plus la montrer aux
    connexions suivantes."""
    with get_connection() as conn:
        conn.execute("UPDATE users SET affichage_guide = 0 WHERE id = ?", (user_id,))


# ---------------------------------------------------------------------------
# Films de référence
# ---------------------------------------------------------------------------

def save_reference_movies(user_id: int, movie_ids: list[int]) -> None:
    """Remplace entièrement la liste des films de référence de l'utilisateur
    (on supprime tout puis on réinsère), et journalise chaque film dans
    l'historique avec le statut 'favorite'."""
    movie_ids = list(dict.fromkeys(int(m) for m in movie_ids))  # dédoublonne, garde l'ordre
    if not (1 <= len(movie_ids) <= 4):
        raise ValueError("Vous devez sélectionner entre un et quatre films.")

    today = date.today().isoformat()
    with get_connection() as conn:
        conn.execute("DELETE FROM reference_movies WHERE user_id = ?", (user_id,))
        conn.executemany(
            "INSERT INTO reference_movies (user_id, movie_id, date_added) VALUES (?, ?, ?)",
            [(user_id, movie_id, today) for movie_id in movie_ids],
        )
        conn.executemany(
            "INSERT INTO history (user_id, movie_id, status, date) VALUES (?, ?, 'favorite', ?)",
            [(user_id, movie_id, today) for movie_id in movie_ids],
        )


# même fonction, juste un nom différent pour l'appeler depuis l'écran de modification
update_reference_movies = save_reference_movies


def get_reference_movies(user_id: int) -> list[int]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT movie_id FROM reference_movies WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
    return [row["movie_id"] for row in rows]


# ---------------------------------------------------------------------------
# Calendriers mensuels
# ---------------------------------------------------------------------------

def get_calendar(user_id: int, month: str) -> sqlite3.Row | None:
    """month au format 'YYYY-MM'. Retourne None s'il n'y a pas encore de
    calendrier pour ce mois — c'est ce None qui déclenche la génération
    d'un nouveau programme dans calendar_engine.py."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM calendars WHERE user_id = ? AND month = ?",
            (user_id, month),
        ).fetchone()


def get_calendar_by_id(calendar_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM calendars WHERE id = ?", (calendar_id,)
        ).fetchone()


def get_active_calendar(user_id: int) -> sqlite3.Row | None:
    """Le calendrier du mois en cours (statut 'active' — un seul à la fois,
    tous les précédents sont 'archived')."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM calendars WHERE user_id = ? AND status = 'active' "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ).fetchone()


def update_calendar_references(calendar_id: int, reference_movie_ids: list[int]) -> None:
    """Met à jour l'instantané des films de référence associé à un
    calendrier (utilisé quand on modifie ses références en cours de mois,
    pour que les remplacements suivants se basent sur le nouveau profil)."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE calendars SET reference_movie_ids = ? WHERE id = ?",
            (json.dumps(reference_movie_ids), calendar_id),
        )


def archive_active_calendars(user_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE calendars SET status = 'archived' WHERE user_id = ? AND status = 'active'",
            (user_id,),
        )


def create_calendar(user_id: int, month: str, reference_movie_ids: list[int]) -> int:
    """Crée le calendrier du mois. reference_movie_ids est sauvegardé tel
    quel (converti en texte JSON) pour garder une trace des films utilisés
    au moment de la génération, même si l'utilisateur change ses références
    plus tard dans le mois."""
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO calendars (user_id, month, status, reference_movie_ids, created_at) "
            "VALUES (?, ?, 'active', ?, ?)",
            (user_id, month, json.dumps(reference_movie_ids), date.today().isoformat()),
        )
        return cursor.lastrowid


def add_recommendation(calendar_id: int, movie_id: int, week: int, status: str = "scheduled") -> int:
    now = date.today().isoformat()
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO recommendations (calendar_id, movie_id, week, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (calendar_id, movie_id, week, status, now, now),
        )
        return cursor.lastrowid


def get_calendar_recommendations(calendar_id: int) -> list[sqlite3.Row]:
    """Toutes les lignes de recommandation d'un calendrier, y compris les
    anciennes (déjà remplacées) — c'est calendar_engine.py qui filtre pour
    ne garder que la plus récente de chaque semaine à l'affichage."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM recommendations WHERE calendar_id = ? ORDER BY week",
            (calendar_id,),
        ).fetchall()


def get_recommendation(recommendation_id: int) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM recommendations WHERE id = ?", (recommendation_id,)
        ).fetchone()


def update_recommendation_status(
    recommendation_id: int, status: str, rating_feedback: str | None = None
) -> None:
    if status not in STATUTS_RECOMMANDATION:
        raise ValueError(f"Statut de recommandation inconnu : {status}")
    with get_connection() as conn:
        conn.execute(
            "UPDATE recommendations SET status = ?, rating_feedback = ?, updated_at = ? "
            "WHERE id = ?",
            (status, rating_feedback, date.today().isoformat(), recommendation_id),
        )


def record_history(user_id: int, movie_id: int, status: str) -> None:
    """Ajoute une ligne d'historique. Contrairement à update_recommendation_
    status, on n'écrase jamais une ligne existante : chaque action laisse
    une trace permanente (utile pour "Mon historique", qui doit rester
    disponible même après le remplacement d'une recommandation)."""
    if status not in STATUTS_HISTORIQUE:
        raise ValueError(f"Statut d'historique inconnu : {status}")
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO history (user_id, movie_id, status, date) VALUES (?, ?, ?, ?)",
            (user_id, movie_id, status, date.today().isoformat()),
        )


def get_user_history(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM history WHERE user_id = ? AND status IN ('watched', 'already_seen') "
            "ORDER BY date DESC, id DESC",
            (user_id,),
        ).fetchall()


def get_archived_calendars(user_id: int) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM calendars WHERE user_id = ? AND status = 'archived' "
            "ORDER BY month DESC",
            (user_id,),
        ).fetchall()


def get_excluded_movie_ids(user_id: int) -> set[int]:
    """Films que le moteur de recommandation ne doit plus jamais proposer :
    références actuelles, films déjà vus, refusés, ou déjà présents dans un
    calendrier (actif ou archivé).

    Le troisième UNION est volontairement large : il prend TOUS les films
    déjà apparus dans un calendrier, quel que soit leur statut (y compris
    "watched" ou même "scheduled"). Ça évite qu'un film déjà proposé un
    mois donné revienne un autre mois, même s'il n'a jamais été noté."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT movie_id FROM reference_movies WHERE user_id = ? "
            "UNION "
            "SELECT movie_id FROM history WHERE user_id = ? AND status IN ('already_seen', 'not_interested') "
            "UNION "
            "SELECT r.movie_id FROM recommendations r "
            "JOIN calendars c ON c.id = r.calendar_id "
            "WHERE c.user_id = ?",
            (user_id, user_id, user_id),
        ).fetchall()
    return {row["movie_id"] for row in rows}


def get_recently_recommended_movie_ids(user_id: int, months: int = 3) -> set[int]:
    """Films recommandés au cours des 3 derniers mois où l'utilisateur a eu
    un calendrier (pas forcément les 3 derniers mois calendaires — si
    l'utilisateur revient après une pause, on compte les 3 derniers mois où
    il a réellement eu un programme)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT r.movie_id, c.month FROM recommendations r "
            "JOIN calendars c ON c.id = r.calendar_id "
            "WHERE c.user_id = ? ORDER BY c.month DESC",
            (user_id,),
        ).fetchall()
    recent_months = sorted({row["month"] for row in rows}, reverse=True)[:months]
    return {row["movie_id"] for row in rows if row["month"] in recent_months}
