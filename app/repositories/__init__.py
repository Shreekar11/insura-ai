"""Repository layer modules."""

from app.repositories.ocr_repository import OCRRepository
from app.repositories.table_repository import TableRepository

__all__ = [
    "OCRRepository",
    "TableRepository",
]
