
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

# Shared database location
PROJECT_FOLDER = Path(__file__).resolve().parent.parent
DATABASE_FOLDER = PROJECT_FOLDER / "database"
DATABASE_FOLDER.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATABASE_FOLDER / "storage.db"


def current_time():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS file_metadata (
                stored_name TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                file_type TEXT NOT NULL,
                upload_time TEXT NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0,
                last_accessed TEXT,
                storage_class TEXT NOT NULL DEFAULT 'Standard'
            )
        """)


def register_file(stored_name, original_name, file_size):
    file_type = Path(original_name).suffix.lower() or "unknown"

    with get_connection() as connection:
        connection.execute("""
            INSERT INTO file_metadata (
                stored_name,
                original_name,
                file_size,
                file_type,
                upload_time,
                access_count,
                last_accessed,
                storage_class
            )
            VALUES (?, ?, ?, ?, ?, 0, NULL, 'Standard')
            ON CONFLICT(stored_name) DO UPDATE SET
                original_name = excluded.original_name,
                file_size = excluded.file_size,
                file_type = excluded.file_type
        """, (
            stored_name,
            original_name,
            file_size,
            file_type,
            current_time()
        ))


def record_access(stored_name):
    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE file_metadata
            SET access_count = access_count + 1,
                last_accessed = ?
            WHERE stored_name = ?
        """, (current_time(), stored_name))

        return cursor.rowcount > 0


def delete_metadata(stored_name):
    with get_connection() as connection:
        cursor = connection.execute("""
            DELETE FROM file_metadata
            WHERE stored_name = ?
        """, (stored_name,))

        return cursor.rowcount > 0


def get_all_metadata():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT *
            FROM file_metadata
            ORDER BY upload_time DESC
        """).fetchall()

        return [dict(row) for row in rows]


def update_storage_class(stored_name, storage_class):
    allowed_classes = {"Standard", "Infrequent", "Archive"}

    if storage_class not in allowed_classes:
        raise ValueError("Invalid storage class")

    with get_connection() as connection:
        cursor = connection.execute("""
            UPDATE file_metadata
            SET storage_class = ?
            WHERE stored_name = ?
        """, (storage_class, stored_name))

        return cursor.rowcount > 0


if __name__ == "__main__":
    init_db()
    print("Metadata database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")
