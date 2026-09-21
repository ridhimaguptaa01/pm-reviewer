import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path("reviews.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def _column_names(conn, table_name):
    rows = conn.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {
        row[1]
        for row in rows
    }


def init_db():

    with get_connection() as conn:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prd_filename TEXT NOT NULL,
                prd_text TEXT NOT NULL,
                review_status TEXT NOT NULL,
                review_output TEXT NOT NULL,
                supporting_evidence_used INTEGER NOT NULL DEFAULT 0,
                feedback_rating TEXT,
                feedback_comment TEXT,
                created_at TEXT NOT NULL
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewer_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                preference_text TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )

        columns = _column_names(
            conn,
            "reviews"
        )

        migrations = {
            "thread_id": (
                "ALTER TABLE reviews "
                "ADD COLUMN thread_id INTEGER"
            ),
            "version_number": (
                "ALTER TABLE reviews "
                "ADD COLUMN version_number INTEGER "
                "NOT NULL DEFAULT 1"
            ),
            "review_kind": (
                "ALTER TABLE reviews "
                "ADD COLUMN review_kind TEXT "
                "NOT NULL DEFAULT 'initial'"
            ),
            "review_context": (
                "ALTER TABLE reviews "
                "ADD COLUMN review_context TEXT "
                "NOT NULL DEFAULT ''"
            ),
        }

        for column, statement in migrations.items():
            if column not in columns:
                conn.execute(statement)

        # Existing rows become Version 1 of their own thread.
        conn.execute(
            """
            UPDATE reviews
            SET thread_id = id
            WHERE thread_id IS NULL
            """
        )

        conn.execute(
            """
            UPDATE reviews
            SET version_number = 1
            WHERE version_number IS NULL
            """
        )

        conn.execute(
            """
            UPDATE reviews
            SET review_kind = 'initial'
            WHERE review_kind IS NULL
               OR TRIM(review_kind) = ''
            """
        )

        conn.execute(
            """
            UPDATE reviews
            SET review_context = ''
            WHERE review_context IS NULL
            """
        )

        conn.commit()


def save_review(
    prd_filename,
    prd_text,
    review_status,
    review_output,
    supporting_evidence_used=False,
    thread_id=None,
    version_number=1,
    review_kind="initial",
    review_context="",
):

    created_at = datetime.now().isoformat(
        timespec="seconds"
    )

    init_db()

    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO reviews (
                prd_filename,
                prd_text,
                review_status,
                review_output,
                supporting_evidence_used,
                created_at,
                thread_id,
                version_number,
                review_kind,
                review_context
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prd_filename,
                prd_text,
                review_status,
                review_output,
                int(supporting_evidence_used),
                created_at,
                thread_id,
                version_number,
                review_kind,
                review_context.strip(),
            )
        )

        review_id = cursor.lastrowid

        if thread_id is None:
            conn.execute(
                """
                UPDATE reviews
                SET thread_id = ?
                WHERE id = ?
                """,
                (
                    review_id,
                    review_id,
                )
            )

        conn.commit()

        return review_id


def get_all_reviews():

    init_db()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                id,
                prd_filename,
                review_status,
                supporting_evidence_used,
                created_at,
                thread_id,
                version_number,
                review_kind
            FROM reviews
            ORDER BY id DESC
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def get_review(review_id):

    init_db()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT *
            FROM reviews
            WHERE id = ?
            """,
            (review_id,)
        ).fetchone()

        if row is None:
            return None

        return dict(row)


def get_thread_reviews(thread_id):

    init_db()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT *
            FROM reviews
            WHERE thread_id = ?
            ORDER BY version_number ASC, id ASC
            """,
            (thread_id,)
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def get_latest_review(thread_id):

    init_db()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        row = conn.execute(
            """
            SELECT *
            FROM reviews
            WHERE thread_id = ?
            ORDER BY version_number DESC, id DESC
            LIMIT 1
            """,
            (thread_id,)
        ).fetchone()

        if row is None:
            return None

        return dict(row)


def get_review_threads():
    """
    Return one sidebar item per review thread.

    The thread title comes from Version 1 while the latest row supplies
    current status/version metadata.
    """

    init_db()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT *
            FROM reviews
            ORDER BY id DESC
            """
        ).fetchall()

    grouped = {}

    for row in rows:
        item = dict(row)
        thread_id = item["thread_id"]

        if thread_id not in grouped:
            grouped[thread_id] = {
                "thread_id": thread_id,
                "latest_review_id": item["id"],
                "latest_version": item["version_number"],
                "latest_review_output": item["review_output"],
                "latest_created_at": item["created_at"],
                "thread_title": item["prd_filename"],
            }

        # Rows are DESC, so later assignments encountered here are older.
        # The oldest filename becomes the stable thread title.
        grouped[thread_id]["thread_title"] = (
            item["prd_filename"]
        )

    threads = list(grouped.values())

    threads.sort(
        key=lambda item: item["latest_review_id"],
        reverse=True
    )

    # Legacy builds could create multiple root threads for the exact same
    # work filename. Collapse those duplicate sidebar entries while keeping
    # every database row intact. The most recently reviewed thread becomes
    # the visible/canonical thread for that title. New revisions are already
    # saved into that same thread_id, so duplicates do not continue growing.
    visible_threads = []
    seen_titles = set()

    for thread in threads:
        normalized_title = (
            thread["thread_title"]
            .strip()
            .casefold()
        )

        if normalized_title in seen_titles:
            continue

        seen_titles.add(
            normalized_title
        )
        visible_threads.append(
            thread
        )

    return visible_threads


def save_feedback(
    review_id,
    rating,
    comment
):

    with get_connection() as conn:

        conn.execute(
            """
            UPDATE reviews
            SET
                feedback_rating = ?,
                feedback_comment = ?
            WHERE id = ?
            """,
            (
                rating,
                comment,
                review_id,
            )
        )

        conn.commit()


def add_reviewer_preference(
    preference_text
):
    """
    Save or reactivate a reusable manager review rule.

    Returns True if a new/re-activated rule was created.
    Returns False if the same rule was already active.
    """

    preference_text = (
        preference_text.strip()
    )

    if not preference_text:
        return False

    init_db()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        existing = conn.execute(
            """
            SELECT id, is_active
            FROM reviewer_preferences
            WHERE preference_text = ?
            """,
            (preference_text,)
        ).fetchone()

        if existing:

            if existing["is_active"]:

                return False

            conn.execute(
                """
                UPDATE reviewer_preferences
                SET is_active = 1
                WHERE id = ?
                """,
                (existing["id"],)
            )

            conn.commit()

            return True

        conn.execute(
            """
            INSERT INTO reviewer_preferences (
                preference_text,
                is_active,
                created_at
            )
            VALUES (?, 1, ?)
            """,
            (
                preference_text,
                datetime.now().isoformat(
                    timespec="seconds"
                ),
            )
        )

        conn.commit()

        return True


def get_reviewer_preferences():
    """
    Return all currently active reusable manager rules.
    """

    init_db()

    with get_connection() as conn:

        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            """
            SELECT
                id,
                preference_text,
                created_at
            FROM reviewer_preferences
            WHERE is_active = 1
            ORDER BY id ASC
            """
        ).fetchall()

        return [
            dict(row)
            for row in rows
        ]


def remove_reviewer_preference(
    preference_id
):
    """
    Deactivate a reviewer rule without deleting its history.
    """

    init_db()

    with get_connection() as conn:

        conn.execute(
            """
            UPDATE reviewer_preferences
            SET is_active = 0
            WHERE id = ?
            """,
            (preference_id,)
        )

        conn.commit()
