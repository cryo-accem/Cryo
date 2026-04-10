import os
import urllib.parse
import pymysql
import pymysql.cursors


DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise Exception("DATABASE_URL environment variable is not set.")


def get_db():
    url = urllib.parse.urlparse(DATABASE_URL)
    database = url.path.lstrip("/").split("?")[0].strip()

    return pymysql.connect(
        host=url.hostname.strip(),
        user=url.username,
        password=url.password,
        database=database,
        port=url.port or 3306,
        ssl={"ssl": {}},
        cursorclass=pymysql.cursors.DictCursor,
    )


def _drop_unique_email(cur, table: str):
    """
    Safely drop ANY unique index on the 'email' column in the given table.
    Queries information_schema to find the actual index name — works on Aiven
    regardless of what MySQL named it (could be 'email', 'email_2', etc.)
    """
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

    # ── NEW: screening_bookings ───────────────────────────────────────────────
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
