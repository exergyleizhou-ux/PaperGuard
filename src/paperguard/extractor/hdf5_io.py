"""HDF5 extractor — turn `.h5` / `.hdf5` files into DataFrames.

Industrial historians (OSIsoft PI archives, InfluxDB exports,
custom DAQ systems) often dump their data to HDF5. PaperGuard's
existing A1-A7 / D1 / D2 / I1-I2 detectors all want a
``pandas.DataFrame``, so this is a thin adapter that:

  1. Opens the file with ``h5py``.
  2. Walks the group tree.
  3. For each leaf dataset that is a 2-D numeric array OR a record
     array with column names, produces a ``DataFrame`` keyed by
     dataset path.

Failure modes (silent):
  - h5py not installed → returns {} + logged warning
  - File is not HDF5 → returns {}
  - Dataset has > 1 M rows → truncated to 1 M with warning
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

MAX_ROWS_PER_DATASET = 1_000_000


def extract_hdf5_tables(path: Path) -> dict[str, pd.DataFrame]:
    """Return ``{dataset_path: DataFrame}`` for every tabular leaf in
    the HDF5 file.

    Treats:
      - 2-D float / int arrays → DataFrame with columns ``col_0..col_N``
      - 1-D record arrays with named dtype fields → DataFrame keyed
        by field names
      - 1-D scalar arrays → single-column DataFrame
    """
    try:
        import h5py  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "extract_hdf5_tables: h5py not installed; pip install h5py"
        )
        return {}

    if not path.exists():
        return {}
    try:
        if not h5py.is_hdf5(str(path)):
            return {}
    except Exception as e:  # noqa: BLE001
        logger.warning("extract_hdf5_tables: %s not HDF5: %s", path, e)
        return {}

    out: dict[str, pd.DataFrame] = {}

    def visit(name: str, obj: object) -> None:
        if not isinstance(obj, h5py.Dataset):
            return
        try:
            shape = obj.shape
            dtype = obj.dtype
        except Exception:  # noqa: BLE001
            return
        # Truncate huge datasets to keep RAM under control.
        max_r = (
            min(shape[0], MAX_ROWS_PER_DATASET) if shape else 0
        )
        try:
            if dtype.fields is not None:
                # Record array — has named columns.
                data = obj[:max_r]
                df = pd.DataFrame.from_records(data)
            elif len(shape) == 2:
                data = obj[:max_r]
                df = pd.DataFrame(
                    data,
                    columns=[f"col_{i}" for i in range(shape[1])],
                )
            elif len(shape) == 1:
                data = obj[:max_r]
                df = pd.DataFrame({"value": data})
            else:
                return
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "extract_hdf5_tables: failed to read %s: %s", name, e
            )
            return
        if shape and shape[0] > MAX_ROWS_PER_DATASET:
            logger.warning(
                "extract_hdf5_tables: truncated %s from %d to %d rows",
                name, shape[0], MAX_ROWS_PER_DATASET,
            )
        out[name] = df

    try:
        with h5py.File(str(path), "r") as f:
            f.visititems(visit)
    except Exception as e:  # noqa: BLE001
        logger.warning("extract_hdf5_tables: open failed: %s", e)
        return {}

    return out
