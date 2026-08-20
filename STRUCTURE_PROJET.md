# Structure du projet

Ce document explique à quoi sert chaque fichier du projet, dossier par dossier.

```
RecommandationFilm/
├── app/
│   └── main.py                    interface Streamlit (le point d'entrée de l'app)
├── src/
│   ├── __init__.py                marque src/ comme un package Python (vide)
│   ├── db.py                      accès à la base SQLite
│   ├── recommender.py             moteur de recommandation
│   ├── calendar_engine.py         orchestration du calendrier mensuel
│   └── posters.py                 récupération et cache des affiches (API TMDB)
├── tests/
│   └── test_parcours.py           tests automatisés
├── models/                        modèle entraîné (sortie du notebook 5)
├── data/                          données brutes, nettoyées, enrichies
├── notebooks/                     les 5 notebooks (partie data)
├── requirements.txt               dépendances Python du projet
├── .gitignore                     fichiers à ne pas committer
├── .env                           clé API TMDB (non commité, à créer soi-même)
└── parcours utilisateur.docx      cahier des charges du parcours
```

---

## `app/main.py`

Le seul fichier qu'on lance directement (`streamlit run app/main.py`). Construit toutes les pages de l'application : accueil, inscription/login, présentation, sélection des films de référence, confirmation, programme mensuel, espace personnel (références/historique/anciens programmes).

Ce fichier ne contient aucune logique métier lourde — il appelle `db.py` pour lire/écrire des données et `calendar_engine.py` pour générer ou modifier le programme, et se contente d'afficher le résultat. C'est volontaire : si demain on change l'algorithme de recommandation, on ne touche pas à `main.py`.

## `src/db.py`

Toute la persistance : ouverture de la base SQLite (`data/app.db`), création des 5 tables (`users`, `reference_movies`, `calendars`, `recommendations`, `history`), et une fonction par opération (`create_user`, `save_reference_movies`, `get_calendar`, `record_history`, etc.). C'est le seul fichier qui écrit du SQL — aucun autre fichier n'accède directement à la base.

## `src/recommender.py`

Le moteur de recommandation à proprement parler. Charge le modèle entraîné (`models/modele_content_enrichi.pkl`), le catalogue (`models/films_content_enrichi.csv`), et récupère aussi le synopsis directement dans `data/enrichi/films_complet.csv` (jamais gardé dans le catalogue final du notebook 5). Expose :
- `search_movies` — recherche par titre, réalisateur ou année, insensible à la casse, aux accents et aux espaces
- `popular_movies` — les films les mieux notés, pour "Aidez-moi à choisir"
- `top_genres` / `top_movies_by_genre` — les genres les plus représentés et leurs meilleurs films, pour "Top recommandations par genre"
- `build_profile` — construit le profil utilisateur (moyenne des films de référence)
- `recommend` — calcule les scores et retourne les meilleurs films, en excluant les films dont les données sont trop incomplètes (`donnees_suffisantes` : il faut au moins acteurs ou mots-clés, un réalisateur, ET un synopsis — sans quoi le score se retrouve artificiellement gonflé, un bug rencontré et corrigé à plusieurs reprises)
- `explain_recommendation` — génère le texte "Pourquoi ce film ?"

C'est le fichier qui a été détaillé dans nos échanges précédents (TF-IDF, similarité cosinus, pondération des 5 catégories).

## `src/calendar_engine.py`

Fait le lien entre `db.py` et `recommender.py` pour appliquer les règles métier : générer le programme du mois, garder le calendrier stable tant qu'on reste dans le même mois, remplacer immédiatement un film marqué "déjà vu" ou "pas intéressé", renouveler le programme quand les films de référence changent (sauf les semaines déjà "regardées"), exclure définitivement les films déjà vus/refusés.

## `src/posters.py`

Récupère l'affiche d'un film via l'API TMDB (le même service que le notebook 4, mais un seul film à la fois plutôt que tout le catalogue d'un coup) et la met en cache dans `models/posters_cache.json` pour ne jamais la redemander deux fois. Nécessite une clé API dans le fichier `.env` (`TMDB_API_KEY=...`) — sans clé, `get_poster_url` renvoie `None` et l'app fonctionne normalement, simplement sans affiches.

## `tests/test_parcours.py`

32 tests automatisés (`pytest`) qui vérifient le parcours complet sans passer par l'interface : création de profil, recherche (titre, réalisateur, année, espaces ignorés), sélection (min/max, doublons), top genres, génération du calendrier, stabilité mensuelle, remplacement immédiat, historique, renouvellement des références, format des titres, affiches (avec et sans clé API), synopsis (présence, secours en anglais, non-régression sur le gonflement de score). Se lance avec `./venv/bin/python -m pytest tests/`.

---

## `models/` — ce que le notebook 5 a produit

| Fichier | Utilisé par l'app ? | Rôle |
|---|---|---|
| `modele_content_enrichi.pkl` (6,1 Mo) | **Oui** | Contient `matrice_combinee` (un vecteur par film) et les poids des 5 catégories. C'est LE fichier dont dépend tout le moteur de recommandation. **Reconstruit une fois par mes soins** (avec le même code que le notebook 5) après l'ajout des synopsis de secours en anglais — sinon le texte affiché aurait changé sans que le score en tienne compte, ce qui aurait recréé le bug du score gonflé pour ces 608 films. |
| `films_content_enrichi.csv` (2,7 Mo) | **Oui** | Le catalogue : movieId, titre, genres, année, réalisateur, acteurs, mots-clés. Une ligne = un film, dans le même ordre que les lignes de `matrice_combinee`. |
| `matrice_tfidf.pkl` (300 Ko) | Non | Matrice TF-IDF des genres seuls (intermédiaire du notebook 5, réutilisé pour construire `matrice_combinee`, pas consulté directement par l'app). |
| `matrice_combinee.pkl` (4,7 Mo) | Non | Une copie de la même matrice que celle contenue dans `modele_content_enrichi.pkl`, sauvegardée séparément à un moment du notebook — redondante pour l'app. |
| `matrice_similarite.pkl` (724 Mo) | Non | Matrice de similarité film × film **déjà calculée à l'avance** pour tous les couples de films (9742 × 9742 scores). L'app ne s'en sert pas : elle calcule la similarité **à la demande**, entre le profil et tous les films, avec `cosine_similarity` — un seul calcul rapide plutôt que de charger 724 Mo en mémoire. |
| `similarite_combinee.pkl` (724 Mo) | Non | Même chose que ci-dessus mais sur `matrice_combinee`. Inutilisé pour la même raison. |
| `vectoriseur_tfidf.pkl` (1 Ko) | Non | L'objet `TfidfVectorizer` entraîné sur les genres (utile pour transformer un *nouveau* texte en vecteur — pas nécessaire ici puisqu'on ne travaille qu'avec des films déjà dans le catalogue). |

*(Note : ces deux gros fichiers de 724 Mo à eux seuls pourraient être supprimés sans rien casser dans l'app — ils ne sont référencés nulle part dans `src/`.)*

---

## `data/` — les données, à chaque étape du nettoyage

- **`data/brute/`** — les fichiers MovieLens originaux, jamais modifiés (`movies.csv`, `ratings.csv`, `tags.csv`, `links.csv`).
- **`data/nettoye/`** — après le notebook 1 : doublons enlevés, dates converties, année extraite du titre, genres nettoyés.
- **`data/enrichi/`** — après le notebook 4 : les films nettoyés + les infos récupérées via l'API TMDB (synopsis, réalisateur, acteurs, mots-clés). `films_complet.csv` est la version finale, c'est elle qui sert de base au notebook 5 pour produire `models/films_content_enrichi.csv` — et c'est aussi ce fichier que `recommender.py` relit directement pour le synopsis (voir ci-dessous).
  - À l'origine, 730 films (7,5%) n'avaient pas de synopsis français. Sur ces 730 : 8 n'ont aucune correspondance TMDB, et parmi les 722 restants, TMDB n'a tout simplement pas de traduction française pour 114 d'entre eux — mais a bien une description en anglais pour les 608 autres. Ces 608 ont été complétés avec le synopsis anglais (colonne `synopsis_anglais` = `True`), affiché dans l'app avec la mention *(en anglais)*. Couverture finale : 98,8% du catalogue (9620/9742).

## `notebooks/` — le travail côté data

| Notebook | Contenu |
|---|---|
| `01_explorations.ipynb` | Chargement, nettoyage et exploration du jeu de données MovieLens brut. |
| `02_content_based.ipynb` | Premier modèle de recommandation, basé uniquement sur les genres (TF-IDF + similarité cosinus). |
| `03_collaboratif.ipynb` | Filtrage collaboratif item-based (matrice utilisateur × film), évalué avec Precision@k/Recall@k. |
| `04_tmdb.ipynb` | Enrichissement du catalogue via l'API TMDB (synopsis, réalisateur, acteurs, mots-clés). |
| `05_contenu_enrichi.ipynb` | Le modèle final : combine les 5 catégories pondérées, construit `matrice_combinee`, évalue le modèle — c'est sa sortie que `recommender.py` utilise. |

---

## Fichiers à la racine

- **`requirements.txt`** — la liste des librairies Python nécessaires, avec un commentaire par ligne expliquant à quoi chacune sert.
- **`.env`** — contient `TMDB_API_KEY=...`, la clé API utilisée par `src/posters.py` pour récupérer les affiches. Jamais commité (voir `.gitignore`) : chaque personne qui installe le projet doit créer ce fichier elle-même avec sa propre clé (gratuite sur themoviedb.org). Sans ce fichier, l'app tourne quand même, juste sans affiches.
- **`.gitignore`** — indique à git de ne pas suivre certains fichiers : `venv/` (spécifique à chaque machine), `*.pyc`/`__pycache__/` (fichiers générés automatiquement par Python), `*.db` (la base de données locale, propre à chaque installation), `.env` (la clé API, secrète), `models/posters_cache.json` (cache généré automatiquement), et la plupart des `.pkl` (trop volumineux — sauf `modele_content_enrichi.pkl`, dont l'app a besoin pour fonctionner après un `git clone`).
- **`parcours utilisateur.docx`** — le document de référence qui décrit tous les écrans et règles métier attendus (c'est le cahier des charges à partir duquel `app/main.py` et `calendar_engine.py` ont été construits). Les affiches ("l'affiche" dans les sections 4.1 et 7) y étaient déjà prévues — `src/posters.py` vient combler ce point.
