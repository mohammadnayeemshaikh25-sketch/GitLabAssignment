from flask import (
    Flask, request, redirect, url_for,
    send_from_directory, render_template_string, abort
)
from werkzeug.utils import secure_filename
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
import shutil

from member2_metadata.metadata import (
    init_db,
    register_file,
    record_access,
    delete_metadata,
    get_all_metadata,
    update_storage_class
)

app = Flask(__name__)

PROJECT_FOLDER = Path(__file__).resolve().parent
STORAGE_FOLDER = PROJECT_FOLDER / "storage_files"

# Three local storage buckets (folders)
BUCKETS = {
    "Standard": STORAGE_FOLDER / "Standard",
    "Infrequent": STORAGE_FOLDER / "Infrequent",
    "Archive": STORAGE_FOLDER / "Archive"
}

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

init_db()

for folder in BUCKETS.values():
    folder.mkdir(parents=True, exist_ok=True)


def find_file_path(stored_name):
    """Find a file in any of the three storage buckets."""
    for folder in BUCKETS.values():
        candidate = folder / stored_name
        if candidate.is_file():
            return candidate
    return None


def migrate_old_files():
    """
    Move files from the old storage_files root folder into
    the bucket recorded in the database. Existing files are preserved.
    """
    old_files = get_all_metadata()

    for file_info in old_files:
        stored_name = file_info["stored_name"]

        # Already inside one of the new bucket folders
        if find_file_path(stored_name):
            continue

        old_path = STORAGE_FOLDER / stored_name
        if old_path.is_file():
            storage_class = file_info.get("storage_class", "Standard")
            if storage_class not in BUCKETS:
                storage_class = "Standard"

            destination = BUCKETS[storage_class] / stored_name
            shutil.move(str(old_path), str(destination))


# One-time migration of files from the previous folder structure
migrate_old_files()


@app.route("/")
def home():
    files = get_all_metadata()

    # Only show files that exist in one of the bucket folders
    stored_files = []
    for file_info in files:
        actual_path = find_file_path(file_info["stored_name"])
        if actual_path:
            item = dict(file_info)
            item["actual_bucket"] = actual_path.parent.name
            stored_files.append(item)

    total_files = len(stored_files)
    total_storage_mb = sum(
        item["file_size"] for item in stored_files
    ) / 1048576
    total_downloads = sum(
        item["access_count"] for item in stored_files
    )
    most_accessed_file = (
        max(stored_files, key=lambda item: item["access_count"])["original_name"]
        if stored_files else "None"
    )

    bucket_counts = {
        bucket: sum(1 for item in stored_files
                    if item["actual_bucket"] == bucket)
        for bucket in BUCKETS
    }

    return render_template_string("""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Cloud Backup & Storage Optimizer</title>
        <style>
            * { box-sizing: border-box; }
            body {
                font-family: Arial, sans-serif;
                margin: 0; padding: 30px;
                background: #f4f6f9; color: #243b53;
            }
            .container { max-width: 1200px; margin: auto; }
            .card {
                background: white; padding: 22px; margin-bottom: 24px;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,.06);
            }
            h1 { margin-bottom: 8px; }
            h2 { margin-top: 0; }
            .subtitle, .notice { color: #627d98; }
            button, .button {
                display: inline-block; padding: 9px 14px; border: 0;
                border-radius: 5px; background: #2563eb; color: white;
                text-decoration: none; cursor: pointer; font-size: 14px;
            }
            .delete-button { background: #dc2626; }
            .table-wrapper { width: 100%; overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; margin-top: 12px; }
            th, td {
                border: 1px solid #e1e7ef; padding: 12px;
                text-align: left; overflow-wrap: anywhere;
            }
            th { background: #243b53; color: white; }
            tr:nth-child(even) { background: #f4f7fb; }
            .actions { display: flex; gap: 8px; flex-wrap: wrap; }
            .bucket-grid {
                display: grid; grid-template-columns: repeat(3, 1fr);
                gap: 14px;
            }
            .bucket {
                background: #f4f7fb; padding: 16px; border-radius: 8px;
            }
            .bucket strong { display: block; margin-bottom: 6px; }
            @media(max-width: 650px) {
                body { padding: 14px; }
                .card { padding: 15px; }
                .bucket-grid { grid-template-columns: 1fr; }
            }
        </style>
    </head>
    <body>
    <div class="container">
        <h1>Cloud Backup &amp; Storage Optimizer</h1>
        <p class="subtitle">
            Upload files, track usage and organize files into storage buckets.
        </p>

        <section class="card">
            <h2>Usage Statistics</h2>
            <p><strong>Total Files:</strong> {{ total_files }}</p>
            <p><strong>Total Storage Used:</strong>
               {{ "%.2f"|format(total_storage_mb) }} MB</p>
            <p><strong>Total Downloads:</strong> {{ total_downloads }}</p>
            <p><strong>Most Accessed File:</strong> {{ most_accessed_file }}</p>
        </section>

        <section class="card">
            <h2>Storage Buckets</h2>
            <div class="bucket-grid">
                <div class="bucket">
                    <strong>Standard</strong>
                    Frequently accessed files
                    <p><b>{{ bucket_counts["Standard"] }}</b> files</p>
                </div>
                <div class="bucket">
                    <strong>Infrequent</strong>
                    Occasionally accessed files
                    <p><b>{{ bucket_counts["Infrequent"] }}</b> files</p>
                </div>
                <div class="bucket">
                    <strong>Archive</strong>
                    Rarely or never accessed files
                    <p><b>{{ bucket_counts["Archive"] }}</b> files</p>
                </div>
            </div>
        </section>

        <section class="card">
            <h2>Upload a File</h2>
            <form action="{{ url_for('upload') }}" method="post"
                  enctype="multipart/form-data">
                <input type="file" name="file" required>
                <button type="submit">Upload</button>
            </form>
            <p class="notice">Maximum file size: 16 MB. New files enter Standard.</p>
        </section>

        <section class="card">
            <h2>Stored Files</h2>
            {% if stored_files %}
            <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>File Name</th>
                        <th>Storage Bucket</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                {% for file in stored_files %}
                    <tr>
                        <td>{{ file["original_name"] }}</td>
                        <td>{{ file["actual_bucket"] }}</td>
                        <td>
                            <div class="actions">
                                <a class="button"
                                   href="{{ url_for('download',
                                   filename=file['stored_name']) }}">Download</a>
                                <form action="{{ url_for('delete_file',
                                      filename=file['stored_name']) }}"
                                      method="post"
                                      onsubmit="return confirm(
                                      'Delete this file permanently?');">
                                    <button class="delete-button"
                                            type="submit">Delete</button>
                                </form>
                            </div>
                        </td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
            </div>
            {% else %}
                <p>No files uploaded yet.</p>
            {% endif %}
        </section>

        <section class="card">
            <h2>Storage Optimization</h2>
            <p>
                Files are moved between folders according to access frequency
                and the time since their last access.
            </p>
            <form action="{{ url_for('optimize_storage') }}" method="post">
                <button type="submit">Optimize Storage</button>
            </form>
            <p class="notice">
                Rule: 5 or more accesses = Standard; 30–89 days unused =
                Infrequent; 90 or more days unused = Archive.
                Never-accessed files are assigned to Archive.
            </p>
        </section>

        <section class="card">
            <h2>File Metadata and Usage</h2>
            <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>File Name</th>
                        <th>Size (MB)</th>
                        <th>Type</th>
                        <th>Access Count</th>
                        <th>Last Accessed</th>
                        <th>Storage Class</th>
                    </tr>
                </thead>
                <tbody>
                {% for file in stored_files %}
                    <tr>
                        <td>{{ file["original_name"] }}</td>
                        <td>{{ "%.2f"|format(file["file_size"] / 1048576) }}</td>
                        <td>{{ file["file_type"] }}</td>
                        <td>{{ file["access_count"] }}</td>
                        <td>{{ file["last_accessed"] or "Never" }}</td>
                        <td>{{ file["actual_bucket"] }}</td>
                    </tr>
                {% else %}
                    <tr><td colspan="6">No files uploaded yet.</td></tr>
                {% endfor %}
                </tbody>
            </table>
            </div>
        </section>
    </div>
    </body>
    </html>
    """,
        stored_files=stored_files,
        total_files=total_files,
        total_storage_mb=total_storage_mb,
        total_downloads=total_downloads,
        most_accessed_file=most_accessed_file,
        bucket_counts=bucket_counts
    )


@app.route("/upload", methods=["POST"])
def upload():
    uploaded_file = request.files.get("file")

    if not uploaded_file or not uploaded_file.filename:
        return "Please select a file.", 400

    original_name = secure_filename(uploaded_file.filename)
    if not original_name:
        return "Invalid filename.", 400

    stored_name = f"{uuid4().hex}_{original_name}"
    file_path = BUCKETS["Standard"] / stored_name

    try:
        uploaded_file.save(file_path)
        register_file(stored_name, original_name, file_path.stat().st_size)
    except Exception:
        file_path.unlink(missing_ok=True)
        app.logger.exception("Could not save uploaded file or metadata")
        return "Upload failed. Please try again.", 500

    return redirect(url_for("home"))


@app.route("/download/<filename>")
def download(filename):
    safe_name = Path(filename).name
    if safe_name != filename:
        abort(404)

    file_path = find_file_path(safe_name)
    if not file_path:
        return "File not found.", 404

    if not record_access(safe_name):
        return "File metadata not found.", 404

    return send_from_directory(
        str(file_path.parent), file_path.name, as_attachment=True
    )


@app.route("/delete/<filename>", methods=["POST"])
def delete_file(filename):
    safe_name = Path(filename).name
    if safe_name != filename:
        abort(404)

    file_path = find_file_path(safe_name)
    if not file_path:
        return "File not found.", 404

    try:
        file_path.unlink()
        delete_metadata(safe_name)
    except Exception:
        app.logger.exception("Could not delete stored file or metadata")
        return "Could not delete the file. Please try again.", 500

    return redirect(url_for("home"))


@app.route("/optimize", methods=["POST"])
def optimize_storage():
    files = get_all_metadata()
    now = datetime.now(timezone.utc)

    for file_info in files:
        stored_name = file_info["stored_name"]
        source_path = find_file_path(stored_name)

        if not source_path:
            app.logger.warning("File missing from storage: %s", stored_name)
            continue

        access_count = file_info["access_count"]
        last_accessed = file_info["last_accessed"]

        if access_count >= 5:
            new_class = "Standard"
        elif not last_accessed:
            new_class = "Archive"
        else:
            last_date = datetime.fromisoformat(last_accessed)
            if last_date.tzinfo is None:
                last_date = last_date.replace(tzinfo=timezone.utc)

            days_unused = (now - last_date).days

            if days_unused >= 90:
                new_class = "Archive"
            elif days_unused >= 30:
                new_class = "Infrequent"
            else:
                new_class = "Standard"

        destination_folder = BUCKETS[new_class]
        destination_path = destination_folder / stored_name

        # Move the physical file if its bucket needs to change
        if source_path.resolve() != destination_path.resolve():
            try:
                shutil.move(str(source_path), str(destination_path))
            except OSError:
                app.logger.exception("Could not move file: %s", stored_name)
                continue

        # Update database after the file has moved successfully
        try:
            update_storage_class(stored_name, new_class)
        except Exception:
            app.logger.exception(
                "Could not update storage class for: %s", stored_name
            )
            # Try to put the file back if the database update fails
            if source_path != destination_path and destination_path.exists():
                shutil.move(str(destination_path), str(source_path))

    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True)
