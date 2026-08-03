CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    affichage_guide INTEGER DEFAULT 1
);

CREATE TABLE reference_movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    movie_id INTEGER,
    date_added TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE calendars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    month TEXT,
    status TEXT DEFAULT 'active',  -- active / archived
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE recommendations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER,
    movie_id INTEGER,
    week INTEGER,
    status TEXT DEFAULT 'scheduled',  -- scheduled / watched / already_seen / not_interested / replaced
    rating_feedback TEXT,
    FOREIGN KEY(calendar_id) REFERENCES calendars(id)
);

CREATE TABLE history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    movie_id INTEGER,
    status TEXT,  -- watched / already_seen / favorite / not_interested
    date TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id)
);