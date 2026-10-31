
from .metadata import (
    init_db,
    register_file,
    record_access,
    get_all_metadata,
    delete_metadata
)

init_db()

# Add sample files
register_file(
    "test001_notes.pdf",
    "notes.pdf",
    2048
)

register_file(
    "test002_photo.jpg",
    "photo.jpg",
    5120
)

# Simulate three successful downloads of notes.pdf
record_access("test001_notes.pdf")
record_access("test001_notes.pdf")
record_access("test001_notes.pdf")

# Display all records
for file in get_all_metadata():
    print(file)

# Remove the sample records after testing
delete_metadata("test001_notes.pdf")
delete_metadata("test002_photo.jpg")
