# Guide utilisateur — Filmolik

Ce guide explique comment utiliser l'application, écran par écran. Pour la structure technique du projet, voir [STRUCTURE_PROJET.md](STRUCTURE_PROJET.md).

## Sommaire

1. [Accéder à l'application](#1-accéder-à-lapplication)
2. [Créer un compte ou se connecter](#2-créer-un-compte-ou-se-connecter)
3. [Choisir ses films de référence](#3-choisir-ses-films-de-référence)
4. [Le programme du mois](#4-le-programme-du-mois)
5. [Réagir à une recommandation](#5-réagir-à-une-recommandation)
6. [L'espace personnel](#6-lespace-personnel)
7. [Bon à savoir](#7-bon-à-savoir)

---

## 1. Accéder à l'application

### 1.1 Sans rien installer (navigateur uniquement)

Si quelqu'un a mis l'application en ligne (voir l'encadré ci-dessous), il suffit d'ouvrir le lien fourni dans n'importe quel navigateur — aucune installation, ni de Python ni de Streamlit, n'est nécessaire. C'est la façon la plus simple d'y accéder pour quelqu'un qui veut juste l'essayer (un correcteur, un camarade...).

> **Pas encore de lien disponible ?** L'application n'est pas hébergée par défaut — elle doit d'abord être déployée une fois par la personne qui gère le projet. La façon la plus simple et gratuite est **Streamlit Community Cloud** :
> 1. Le code doit être sur GitHub (déjà fait — voir les dépôts du projet)
> 2. Créer un compte sur [share.streamlit.io](https://share.streamlit.io) (connexion via GitHub)
> 3. Cliquer sur "New app", choisir le dépôt et indiquer `RecommandationFilm/app/main.py` comme fichier principal
> 4. Dans les réglages de l'app, section **"Secrets"**, ajouter la clé API TMDB au même format que le fichier `.env` local : `TMDB_API_KEY = "..."` (le fichier `.env` n'est jamais envoyé sur GitHub, donc cette étape est nécessaire pour que les affiches s'affichent en ligne)
> 5. Streamlit Cloud installe automatiquement les dépendances (`requirements.txt`) et donne une adresse publique du type `https://....streamlit.app`, à partager avec qui on veut
>
> Petite différence par rapport à une utilisation en local : sur l'offre gratuite, le stockage n'est pas garanti permanent — la base de données (comptes, historique) peut occasionnellement être réinitialisée si l'application redémarre après une période d'inactivité.

### 1.2 En local

#### Si Python n'est pas installé du tout

- **Windows** : télécharger l'installeur sur [python.org/downloads](https://www.python.org/downloads/), le lancer, et **cocher la case "Add python.exe to PATH"** en bas du premier écran avant de cliquer sur "Install Now" — c'est l'étape la plus souvent oubliée, sans elle la commande `python` ne sera pas reconnue dans le terminal.
- **Mac** : télécharger l'installeur sur [python.org/downloads](https://www.python.org/downloads/) (ou, pour qui a déjà [Homebrew](https://brew.sh), `brew install python`), puis suivre l'installeur.

Une fois installé, vérifier dans un terminal (`cmd` ou PowerShell sous Windows, `Terminal` sous Mac) :

```bash
python3 --version
```

*(sous Windows, essayer `python --version` si `python3` n'est pas reconnu)*

N'importe quelle version récente de Python 3 convient — l'application a été testée avec succès jusqu'à Python 3.14, la toute dernière version au moment de l'écriture de ce guide.

#### Première installation du projet (une seule fois)

Après avoir récupéré le dossier `RecommandationFilm` (via `git clone` ou téléchargement du zip) :

```bash
cd chemin/vers/RecommandationFilm
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

*(remplacer `chemin/vers/RecommandationFilm` par l'emplacement réel du dossier sur votre ordinateur — par exemple `cd Documents/RecommandationFilm`. Sous Windows : `python -m venv venv` puis `venv\Scripts\pip install -r requirements.txt`)*

Cette étape crée un environnement virtuel (`venv/`, un dossier isolé propre au projet, pour ne pas mélanger ses librairies avec d'autres projets Python) et y installe tout ce dont l'application a besoin (Streamlit, pandas, scikit-learn...). Elle prend une à deux minutes et n'est à faire qu'une seule fois.

*(Si `streamlit` était déjà installé ailleurs sur la machine dans une version ancienne, ce n'est pas un problème : la commande ci-dessus installe sa propre copie à jour dans `venv/`, indépendante du reste du système. Si malgré tout `./venv/bin/streamlit --version` affiche une version étonnamment ancienne — un souci de cache pip par exemple — on peut forcer une réinstallation propre avec `./venv/bin/pip install --upgrade --force-reinstall streamlit`.)*

#### Lancer l'application (à chaque fois)

```bash
cd chemin/vers/RecommandationFilm
./venv/bin/streamlit run app/main.py
```

*(sous Windows : `venv\Scripts\streamlit run app/main.py`)*

Le navigateur s'ouvre automatiquement sur `http://localhost:8501`. Pour arrêter l'application, `Ctrl+C` dans le terminal.

*(Les affiches de films ont besoin d'une clé API TMDB dans un fichier `.env` — sans elle, l'application fonctionne normalement, simplement sans images.)*

---

## 2. Créer un compte ou se connecter

À l'ouverture, deux boutons :

- **Inscription** — un pseudonyme et un mot de passe suffisent, aucun email n'est demandé. Le pseudonyme doit être unique.
- **Login** — pour un profil déjà créé.

Lors de la toute première inscription, un court écran explique le principe de l'application (choisir des films → recevoir 4 recommandations par mois → signaler ce qui a déjà été vu ou ne plaît pas). Une case **« Ne plus afficher »** permet de ne plus le revoir aux prochaines connexions.

---

## 3. Choisir ses films de référence

C'est ce qui définit vos goûts pour le calcul des recommandations — entre **1 et 4 films**, pas forcément vos films préférés de tous les temps, juste des films qui vous représentent bien.

Trois façons de trouver des films :

- **Rechercher un film** — par titre, par nom de réalisateur, ou par année (ex. `toystory1995`). La recherche ignore les majuscules, les accents et les espaces : `thegodfather` retrouve *The Godfather*.
- **Aidez-moi à choisir** — une liste des films les mieux notés du catalogue, pour repartir sur des valeurs sûres si vous ne savez pas par où commencer.
- **Top recommandations par genre** — cliquez sur un des 8 genres les plus représentés (Drama, Comedy, Action...) pour voir les meilleurs films de ce genre.

Cliquez sur **Ajouter** pour ajouter un film à votre sélection (le bouton devient **Ajouté**, désactivé). Un film déjà ajouté ne peut pas être ajouté deux fois, et impossible de dépasser 4 films — le bouton se désactive automatiquement une fois la limite atteinte. Retirez un film avec le bouton **Retirer** dans la liste **« Mes films sélectionnés »**.

Une fois au moins un film choisi, le bouton en bas change :
- `Continuer avec N film(s)` si vous avez moins de 4 films
- `Créer mon programme du mois` si vous en avez 4

Sur l'écran suivant, un récapitulatif de votre sélection s'affiche avant de lancer le calcul — vous pouvez encore revenir en arrière avec **Modifier ma sélection**, ou valider avec **Générer mon programme**.

---

## 4. Le programme du mois

Le programme est composé de **4 films, un par semaine du mois**. Chaque carte affiche :

- l'affiche du film (si disponible)
- le titre, l'année, le réalisateur, les genres
- **Pourquoi ce film ?** — une courte explication de ce que ce film partage avec vos films de référence (mêmes genres, mots-clés thématiques, ou même réalisateur)
- **Voir l'information supplémentaire** (à déplier) — synopsis, acteurs principaux et mots-clés, quand ces informations existent pour le film. *(Certains films n'ont qu'un synopsis en anglais sur la base de données — c'est indiqué explicitement dans ce cas.)*

Une barre de progression en haut indique combien de films ont déjà été regardés ce mois-ci.

**Le programme ne change jamais tout seul.** Il reste identique pendant tout le mois, même si vous rouvrez l'application plusieurs fois — un nouveau programme n'est généré qu'à votre première connexion du mois suivant.

---

## 5. Réagir à une recommandation

Trois actions possibles sur chaque film du programme :

| Bouton | Signifie | Effet |
|---|---|---|
| **Je l'ai déjà vu** | Vous connaissiez déjà ce film avant qu'il soit recommandé | Ajouté à l'historique, **remplacé immédiatement** par un autre film sur la même semaine |
| **Pas intéressé** | Ce film ne vous tente pas | **Remplacé immédiatement** par un autre film sur la même semaine, jamais reproposé |
| **Regardé après la recommandation** | Vous avez regardé le film grâce au programme | Ajouté à l'historique avec un badge ✓, **reste affiché tel quel** (pas de remplacement) |

**Chaque action demande une confirmation** : un premier clic affiche un message « Confirmer : ... ? » avec deux boutons, **Confirmer** (qui applique réellement l'action) et **Annuler** (qui revient en arrière sans rien changer). Rien n'est modifié tant que vous n'avez pas cliqué sur Confirmer.

Un film marqué « déjà vu » ou « pas intéressé » ne sera plus jamais recommandé par la suite.

---

## 6. L'espace personnel

Trois autres onglets sont disponibles à côté de « Programme actuel » :

- **Mes films de référence** — la liste de vos films de référence actuels, avec un bouton **Modifier mes films de référence**. Changer sa sélection **renouvelle immédiatement** toutes les semaines du programme en cours — sauf celles déjà marquées « Regardé après la recommandation », qui ne bougent pas.
- **Mon historique** — tous les films marqués « déjà vu » ou « regardé après la recommandation », avec leur date.
- **Anciens programmes** — les programmes des mois précédents, archivés et consultables (mais plus modifiables).

Le bouton **Se déconnecter** en bas de page ramène à l'écran d'accueil.

---

## 7. Bon à savoir

- **Un film jamais reproposé** : les films de référence, déjà vus, refusés, ou déjà apparus dans un de vos programmes (même anciens) ne sont plus jamais recommandés.
- **Diversité du programme** : les 4 films du mois évitent autant que possible de partager le même réalisateur.
- **Renouvellement automatique** : à votre première connexion d'un nouveau mois, l'ancien programme est archivé et un nouveau est généré à partir de vos films de référence actuels — aucune action de votre part n'est nécessaire.
- **Si l'application ne trouve pas 4 films** répondant à tous les critères, elle élargit progressivement la recherche (par exemple en levant la contrainte des 3 derniers mois), mais ne recommande jamais un film déjà vu ou refusé.
