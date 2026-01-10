from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Literal, Optional

DatasetType = Literal["articles", "tiers", "supplier_factors", "transport", "customers"]

@dataclass(frozen=True)
class UploadTypeSpec:
    dataset_type: DatasetType
    filename: str
    content_types: tuple[str, ...]  # MIME types
    description: str

UPLOAD_TYPES: Dict[DatasetType, UploadTypeSpec] = {
    "articles": UploadTypeSpec(
        dataset_type="articles",
        filename="articles.csv",
        content_types=("text/csv", "application/csv", "application/vnd.ms-excel"),
        description="Articles master list (CSV).",
    ),
    "tiers": UploadTypeSpec(
        dataset_type="tiers",
        filename="tiers.csv",
        content_types=("text/csv", "application/csv", "application/vnd.ms-excel"),
        description="Tier/staffel rules (CSV).",
    ),
    "supplier_factors": UploadTypeSpec(
        dataset_type="supplier_factors",
        filename="supplier_factors.csv",
        content_types=("text/csv", "application/csv", "application/vnd.ms-excel"),
        description="Supplier factors (CSV).",
    ),
    "transport": UploadTypeSpec(
        dataset_type="transport",
        filename="transport.csv",
        content_types=("text/csv", "application/csv", "application/vnd.ms-excel"),
        description="Transport pricing rules (CSV).",
    ),
    "customers": UploadTypeSpec(
        dataset_type="customers",
        filename="customers.xlsx",
        content_types=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ),
        description="Customer agreements (Excel).",
    ),
}

def get_upload_spec(dataset_type: DatasetType) -> UploadTypeSpec:
    return UPLOAD_TYPES[dataset_type]
