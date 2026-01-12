import os
import uuid
from typing import BinaryIO


BASE_UPLOAD_DIR = "uploads"


def ensure_upload_dir() -> None:
    """
    Create the uploads directory if it does not exist.
    """
    if not os.path.exists(BASE_UPLOAD_DIR):
        os.makedirs(BASE_UPLOAD_DIR)


def save_uploaded_file(file: BinaryIO, original_filename: str) -> str:
    """
    Save an uploaded file (PDF) to disk with a unique name.

    Returns:
        file_path (str): Path to the saved file
    """
    ensure_upload_dir()

    file_extension = os.path.splitext(original_filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(BASE_UPLOAD_DIR, unique_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(file.read())

    return file_path
