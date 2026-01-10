from __future__ import annotations

import os
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.verticals.ace.storage.manifest import (
    build_manifest_for_dataset_dir,
    write_manifest,
    read_manifest,
)

from app.verticals.ace.data_validators.common import (
    parse_csv,
    parse_xlsx,
    get_cell,
    to_str,
    to_int,
    to_decimal,
)

from app.verticals.ace.domain.dataset import DatasetBundle
from app.verticals.ace.domain.models import (
    Article,
    TierRow,
    SupplierFactor,
    TransportRow,
    Customer,
)


# =============================================================================
# Paths (single source for storage locations)
# =============================================================================


def vertical_root() -> Path:
    # .../app/verticals/ace/storage/loader.py -> parents[1] = .../app/verticals/ace
    return Path(__file__).resolve().parents[1]


def data_root() -> Path:
    return vertical_root() / "data"


def staging_root() -> Path:
    return data_root() / "staging"


def active_dir() -> Path:
    return data_root() / "active"


def archive_root() -> Path:
    return data_root() / "archive"


def ensure_base_dirs() -> None:
    staging_root().mkdir(parents=True, exist_ok=True)
    active_dir().mkdir(parents=True, exist_ok=True)
    archive_root().mkdir(parents=True, exist_ok=True)


def staging_dataset_dir(dataset_id: str) -> Path:
    return staging_root() / dataset_id


def archive_dataset_dir(dataset_id: str) -> Path:
    return archive_root() / dataset_id


# =============================================================================
# Atomic activation (2.5) + rollback (2.6)
# =============================================================================


def _lock_path() -> Path:
    return data_root() / ".activation.lock"


@contextmanager
def activation_lock(timeout_seconds: int = 30):
    """
    Simple cross-process lock using exclusive file create.
    Avoids concurrent activate calls.
    """
    ensure_base_dirs()
    lockfile = _lock_path()
    start = time.time()
    fd: int | None = None

    while True:
        try:
            fd = os.open(str(lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            break
        except FileExistsError:
            if time.time() - start > timeout_seconds:
                raise RuntimeError(
                    "Activation lock timeout (another activation in progress)."
                )
            time.sleep(0.1)

    try:
        yield
    finally:
        try:
            if fd is not None:
                os.close(fd)
        finally:
            try:
                lockfile.unlink(missing_ok=True)
            except Exception:
                pass


@dataclass(frozen=True)
class ActivationResult:
    ok: bool
    new_dataset_id: str | None
    previous_archived_id: str | None
    message: str


def _safe_dataset_id(raw: str) -> str:
    return (
        "".join(ch for ch in raw.strip() if ch.isalnum() or ch in ("-", "_"))[:80]
        or "dataset"
    )


def activate_staging_dataset(
    dataset_id: str, *, uploaded_by: str = "admin"
) -> ActivationResult:
    """
    Atomic: replace data/active with staging/<dataset_id> via rename swaps.
    Also writes data/active/manifest.json (2.6) so engine can read activeVersionId.
    """
    ensure_base_dirs()
    dataset_id = _safe_dataset_id(dataset_id)

    src = staging_dataset_dir(dataset_id)
    if not src.exists():
        return ActivationResult(False, None, None, f"Staging dataset not found: {src}")

    archived_id = f"active_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    old_active_tmp = data_root() / f"__active_old__{archived_id}"
    new_active_tmp = data_root() / f"__active_new__{dataset_id}_{uuid.uuid4().hex[:6]}"

    with activation_lock():
        # move staging -> temp
        os.replace(str(src), str(new_active_tmp))

        # move active -> temp old
        if active_dir().exists():
            os.replace(str(active_dir()), str(old_active_tmp))
        else:
            active_dir().mkdir(parents=True, exist_ok=True)
            os.replace(str(active_dir()), str(old_active_tmp))

        # temp new -> active
        os.replace(str(new_active_tmp), str(active_dir()))

        # 2.6: write active manifest (single source of truth)
        mf = build_manifest_for_dataset_dir(
            active_dir(),
            version_id=dataset_id,
            uploaded_by=uploaded_by,
        )
        write_manifest(active_dir(), mf.to_dict())

        # archive old active (best-effort)
        archived_path = archive_dataset_dir(archived_id)
        archived_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.replace(str(old_active_tmp), str(archived_path))
        except Exception:
            invalidate_loaded_cache()
            return ActivationResult(
                True,
                dataset_id,
                None,
                "Activated, but archiving previous active failed (manual cleanup needed).",
            )

    invalidate_loaded_cache()
    return ActivationResult(
        True, dataset_id, archived_id, "Activated staging dataset atomically."
    )


def rollback_to_version(
    version_id: str, *, uploaded_by: str = "admin"
) -> ActivationResult:
    """
    Rollback by activating an archived snapshot folder under data/archive/<version_id>.
    Also writes data/active/manifest.json (2.6).
    """
    ensure_base_dirs()
    version_id = _safe_dataset_id(version_id)

    src = archive_dataset_dir(version_id)
    if not src.exists():
        return ActivationResult(False, None, None, f"Archive version not found: {src}")

    archived_id = f"active_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    old_active_tmp = data_root() / f"__active_old__{archived_id}"
    new_active_tmp = data_root() / f"__active_new__{version_id}_{uuid.uuid4().hex[:6]}"

    with activation_lock():
        os.replace(str(src), str(new_active_tmp))

        if active_dir().exists():
            os.replace(str(active_dir()), str(old_active_tmp))
        else:
            active_dir().mkdir(parents=True, exist_ok=True)
            os.replace(str(active_dir()), str(old_active_tmp))

        os.replace(str(new_active_tmp), str(active_dir()))

        # 2.6: write active manifest for rollback version
        mf = build_manifest_for_dataset_dir(
            active_dir(),
            version_id=version_id,
            uploaded_by=uploaded_by,
        )
        write_manifest(active_dir(), mf.to_dict())

        archived_path = archive_dataset_dir(archived_id)
        try:
            os.replace(str(old_active_tmp), str(archived_path))
        except Exception:
            invalidate_loaded_cache()
            return ActivationResult(
                True,
                version_id,
                None,
                "Rolled back, but archiving previous active failed (manual cleanup needed).",
            )

    invalidate_loaded_cache()
    return ActivationResult(
        True, version_id, archived_id, "Rollback activated atomically."
    )


# =============================================================================
# 2.8 Loaded Data API (read-only, engine-safe) + cache
# =============================================================================

_CACHE: Optional[DatasetBundle] = None
_CACHE_VERSION: Optional[str] = None


def invalidate_loaded_cache() -> None:
    global _CACHE, _CACHE_VERSION
    _CACHE = None
    _CACHE_VERSION = None


def _active_version_id_from_manifest(active_path: Path) -> str:
    mf = read_manifest(active_path)
    v = mf.get("activeVersionId")
    if not isinstance(v, str) or not v:
        raise RuntimeError("Active manifest missing activeVersionId")
    return v


def load_active_bundle(force_reload: bool = False) -> DatasetBundle:
    """
    Engine-safe read-only accessor:
    - reads ONLY from data/active
    - caches in-memory
    - reloads if activeVersionId changed (manifest is single source of truth)
    """
    global _CACHE, _CACHE_VERSION

    ensure_base_dirs()
    active_path = active_dir()
    version_id = _active_version_id_from_manifest(active_path)

    if (not force_reload) and _CACHE is not None and _CACHE_VERSION == version_id:
        return _CACHE

    bundle = _load_bundle_from_dir(active_path, version_id=version_id)
    _CACHE = bundle
    _CACHE_VERSION = version_id
    return bundle


def _load_bundle_from_dir(dataset_dir: Path, *, version_id: str) -> DatasetBundle:
    # ---- articles ----
    a_rows = parse_csv(dataset_dir / "articles.csv")
    articles: dict[str, Article] = {}
    for r in a_rows:
        sku = to_str(get_cell(r, ["SKU"])).upper()
        desc = to_str(get_cell(r, ["Omschrijving"]))
        cost = (
            to_decimal(
                get_cell(r, ["Inkoopprijs"]),
                source=f"{dataset_dir}/articles.csv:Inkoopprijs",
            )
            or 0.0
        )
        cur = to_str(get_cell(r, ["Valuta"])).upper()
        w = (
            to_decimal(
                get_cell(r, ["GewichtKg"]),
                source=f"{dataset_dir}/articles.csv:GewichtKg",
            )
            or 0.0
        )
        if sku:
            articles[sku] = Article(
                sku=sku, description=desc, cost=cost, currency=cur, weight_kg=w
            )

    # ---- tiers ----
    t_rows = parse_csv(dataset_dir / "tiers.csv")
    tiers: list[TierRow] = []
    for r in t_rows:
        v = to_int(get_cell(r, ["Van"])) or 0
        t = to_int(get_cell(r, ["Tot"]))  # may be None
        d = (
            to_decimal(
                get_cell(r, ["KortingPct"]),
                source=f"{dataset_dir}/tiers.csv:KortingPct",
            )
            or 0.0
        )
        tiers.append(TierRow(from_qty=v, to_qty=t, discount_pct=d))
    tiers.sort(key=lambda x: x.from_qty)

    # ---- supplier_factors ----
    s_rows = parse_csv(dataset_dir / "supplier_factors.csv")
    supplier_factors: dict[str, SupplierFactor] = {}
    for r in s_rows:
        name = to_str(get_cell(r, ["Leverancier"])).strip()
        factor = (
            to_decimal(
                get_cell(r, ["Factor"]),
                source=f"{dataset_dir}/supplier_factors.csv:Factor",
            )
            or 1.0
        )
        markup = (
            to_decimal(
                get_cell(r, ["ValutaOpslagPct"]),
                source=f"{dataset_dir}/supplier_factors.csv:ValutaOpslagPct",
            )
            or 0.0
        )
        if name:
            supplier_factors[name.lower()] = SupplierFactor(
                supplier=name, factor=factor, currency_markup_pct=markup
            )

    # ---- transport ----
    tr_rows = parse_csv(dataset_dir / "transport.csv")
    transport: list[TransportRow] = []
    for r in tr_rows:
        pc = to_str(get_cell(r, ["Postcode"])).upper().replace(" ", "")
        zone = to_str(get_cell(r, ["Zone"]))
        eurkg = (
            to_decimal(
                get_cell(r, ["EurPerKg"]),
                source=f"{dataset_dir}/transport.csv:EurPerKg",
            )
            or 0.0
        )
        transport.append(TransportRow(postcode=pc, zone=zone, eur_per_kg=eurkg))

    # ---- customers ----
    c_rows = parse_xlsx(dataset_dir / "customers.xlsx")
    customers: dict[str, Customer] = {}
    for r in c_rows:
        cid = to_str(get_cell(r, ["KlantID"])).strip()
        prof = to_str(get_cell(r, ["Kortingsprofiel"])).upper()
        mx = (
            to_decimal(
                get_cell(r, ["MaxExtraKortingPct"]),
                source=f"{dataset_dir}/customers.xlsx:MaxExtraKortingPct",
            )
            or 0.0
        )
        if cid:
            customers[cid.lower()] = Customer(
                customer_id=cid, discount_profile=prof, max_extra_discount_pct=mx
            )

    return DatasetBundle(
        active_version_id=version_id,
        articles=articles,
        tiers=tiers,
        supplier_factors=supplier_factors,
        transport=transport,
        customers=customers,
    )


# Convenience read-only getters


def get_articles() -> dict[str, Article]:
    return load_active_bundle().articles


def get_tiers() -> list[TierRow]:
    return load_active_bundle().tiers


def get_supplier_factors() -> dict[str, SupplierFactor]:
    return load_active_bundle().supplier_factors


def get_transport_table() -> list[TransportRow]:
    return load_active_bundle().transport


def get_customers() -> dict[str, Customer]:
    return load_active_bundle().customers
