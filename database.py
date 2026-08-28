import os
import sqlite3
import urllib.parse

import pymysql
import pymysql.cursors


DEFAULT_SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preview.db")
DATABASE_URL = os.environ.get("DATABASE_URL") or f"sqlite:///{DEFAULT_SQLITE_PATH}"


def _convert_sqlite_placeholders(query):
    """Convert ? placeholders without changing quoted SQL text."""
    converted = []
    quote = None
    index = 0

    while index < len(query):
        character = query[index]

        if quote:
            converted.append(character)
            if character == quote:
                if index + 1 < len(query) and query[index + 1] == quote:
                    converted.append(query[index + 1])
                    index += 1
                else:
                    quote = None
        elif character in ("'", '"', "`"):
            quote = character
            converted.append(character)
        elif character == "?":
            converted.append("%s")
        else:
            converted.append(character)

        index += 1

    return "".join(converted)


class MySQLDictCursor(pymysql.cursors.DictCursor):
    def execute(self, query, args=None):
        return super().execute(_convert_sqlite_placeholders(query), args)


def _is_sqlite_url():
    return urllib.parse.urlparse(DATABASE_URL).scheme == "sqlite"


def _sqlite_db_path():
    url = urllib.parse.urlparse(DATABASE_URL)
    db_path = url.path or ":memory:"

    if db_path == ":memory:":
        return db_path

    if url.netloc == "" and db_path.startswith("//"):
        db_path = db_path[1:]
    elif url.netloc == "" and db_path.startswith("/"):
        db_path = db_path.lstrip("/")

    if not os.path.isabs(db_path):
        return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), db_path))

    return db_path


def get_db():
    url = urllib.parse.urlparse(DATABASE_URL)

    if _is_sqlite_url():
        db_path = _sqlite_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    database = url.path.lstrip("/").split("?")[0].strip()
    return pymysql.connect(
        host=url.hostname.strip(),
        user=url.username,
        password=url.password,
        database=database,
        port=url.port or 3306,
        ssl={"ssl": {}},
        cursorclass=MySQLDictCursor,
    )


def _drop_unique_email(cur, table: str):
    """
    Safely drop ANY unique index on the 'email' column in the given table.
    For SQLite, there is no information_schema and the preview database is
    intentionally designed without email uniqueness constraints.
    """
    if _is_sqlite_url():
        return

    db = cur.connection.db.decode() if isinstance(cur.connection.db, bytes) else cur.connection.db
    cur.execute("""
        SELECT DISTINCT INDEX_NAME
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME   = %s
          AND COLUMN_NAME  = 'email'
          AND NON_UNIQUE   = 0
          AND INDEX_NAME  != 'PRIMARY'
    """, [db, table])
    rows = cur.fetchall()
    for row in rows:
        idx = row["INDEX_NAME"]
        try:
            cur.execute(f"ALTER TABLE `{table}` DROP INDEX `{idx}`")
        except Exception as e:
            print(f"  Could not drop index {idx} on {table}: {e}")


def init_db():
    """
    Create tables if not exist. Never modifies existing data.
    Safely removes UNIQUE constraint on email in bookings & screening_bookings
    so the same user can re-register after a slot completes.
    """
    conn = get_db()
    cur = conn.cursor()

    # ── Existing tables (safe: IF NOT EXISTS) ────────────────────────────────
    if _is_sqlite_url():
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      VARCHAR(100),
                email         VARCHAR(150) UNIQUE,
                password_hash VARCHAR(255),
                role          TEXT CHECK(role IN ('user', 'admin')) DEFAULT 'user',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name         VARCHAR(100),
                pi_name           VARCHAR(100),
                email             VARCHAR(150),
                origin            VARCHAR(100),
                esm               VARCHAR(150),
                sample_name       VARCHAR(150),
                grids             INTEGER,
                days              INTEGER,
                status            TEXT CHECK(status IN ('waiting', 'ongoing', 'completed')) DEFAULT 'waiting',
                registration_date DATE,
                completion_date   DATE,
                registered_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS freezing_bookings (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name     VARCHAR(100),
                pi_name       VARCHAR(100),
                email         VARCHAR(150),
                origin        VARCHAR(100),
                sample_name   VARCHAR(150),
                grids         INTEGER,
                freezing_date DATE,
                status        TEXT CHECK(status IN ('active', 'completed')) DEFAULT 'active',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS completed_freezing (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name     VARCHAR(100),
                pi_name       VARCHAR(100),
                email         VARCHAR(150),
                origin        VARCHAR(100),
                sample_name   VARCHAR(150),
                grids         INTEGER,
                freezing_date DATE,
                completed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS screening_bookings (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name         VARCHAR(100),
                pi_name           VARCHAR(100),
                email             VARCHAR(150),
                origin            VARCHAR(100),
                esm               VARCHAR(150),
                sample_name       VARCHAR(150),
                grids             INTEGER,
                days              INTEGER,
                status            TEXT CHECK(status IN ('waiting', 'ongoing', 'completed')) DEFAULT 'waiting',
                registration_date DATE,
                completion_date   DATE,
                registered_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                username      VARCHAR(100),
                email         VARCHAR(150) UNIQUE,
                password_hash VARCHAR(255),
                role          ENUM('user','admin') DEFAULT 'user',
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id                INT AUTO_INCREMENT PRIMARY KEY,
                user_name         VARCHAR(100),
                pi_name           VARCHAR(100),
                email             VARCHAR(150),
                origin            VARCHAR(100),
                esm               VARCHAR(150),
                sample_name       VARCHAR(150),
                grids             INT,
                days              INT,
                status            ENUM('waiting','ongoing','completed') DEFAULT 'waiting',
                registration_date DATE,
                completion_date   DATE,
                registered_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS freezing_bookings (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                user_name     VARCHAR(100),
                pi_name       VARCHAR(100),
                email         VARCHAR(150),
                origin        VARCHAR(100),
                sample_name   VARCHAR(150),
                grids         INT,
                freezing_date DATE,
                status        ENUM('active','completed') DEFAULT 'active',
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS completed_freezing (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                user_name     VARCHAR(100),
                pi_name       VARCHAR(100),
                email         VARCHAR(150),
                origin        VARCHAR(100),
                sample_name   VARCHAR(150),
                grids         INT,
                freezing_date DATE,
                completed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS screening_bookings (
                id                INT AUTO_INCREMENT PRIMARY KEY,
                user_name         VARCHAR(100),
                pi_name           VARCHAR(100),
                email             VARCHAR(150),
                origin            VARCHAR(100),
                esm               VARCHAR(150),
                sample_name       VARCHAR(150),
                grids             INT,
                days              INT,
                status            ENUM('waiting','ongoing','completed') DEFAULT 'waiting',
                registration_date DATE,
                completion_date   DATE,
                registered_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    # ── Remove any UNIQUE index on email in bookings & screening_bookings ────
    # Uses information_schema so it finds the real index name on Aiven.
    # Completely safe — if no unique index exists, nothing happens.
    _drop_unique_email(cur, "bookings")
    _drop_unique_email(cur, "screening_bookings")

    conn.commit()
    cur.close()
    conn.close()
