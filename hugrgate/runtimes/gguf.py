"""GGUF model discovery. Slice 160.

Finds ``.gguf`` files on disk and reads their metadata with a
pure-python GGUF header parser — no ``llama.cpp`` required. Only the
header (magic, version, key/value store, tensor *infos*) is read; the
tensor blobs are never touched, so scanning a directory of
multi-gigabyte files is cheap.

:func:`discover_gguf_models` returns one :class:`GGUFModel` per file,
with ``error`` set (instead of raising) for corrupt/truncated files so
a single bad file never aborts a directory scan.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.errors import GGUFError

#: GGUF magic bytes.
GGUF_MAGIC = b"GGUF"

#: GGUF version this parser targets.
GGUF_VERSION = 3

#: ``general.file_type`` integer -> quantization label (common values).
FILE_TYPES = {
    0: "ALL_F32",
    1: "MOSTLY_F16",
    2: "MOSTLY_Q4_0",
    3: "MOSTLY_Q4_1",
    6: "MOSTLY_Q4_1_SOME_F16",
    7: "MOSTLY_Q8_0",
    8: "MOSTLY_Q5_0",
    9: "MOSTLY_Q5_1",
    10: "MOSTLY_Q2_K",
    11: "MOSTLY_Q3_K_S",
    12: "MOSTLY_Q3_K_M",
    13: "MOSTLY_Q3_K_L",
    14: "MOSTLY_Q4_K_S",
    15: "MOSTLY_Q4_K_M",
    16: "MOSTLY_Q5_K_S",
    17: "MOSTLY_Q5_K_M",
    18: "MOSTLY_Q6_K",
    19: "MOSTLY_IQ2_XXS",
    20: "MOSTLY_IQ2_XS",
    21: "MOSTLY_Q2_K_S",
    22: "MOSTLY_IQ3_XS",
    23: "MOSTLY_IQ3_XXS",
    24: "MOSTLY_IQ1_S",
    25: "MOSTLY_IQ4_NL",
    26: "MOSTLY_IQ3_S",
    27: "MOSTLY_IQ3_M",
    28: "MOSTLY_IQ2_S",
    29: "MOSTLY_IQ2_M",
    30: "MOSTLY_IQ4_XS",
    31: "MOSTLY_IQ1_M",
    32: "MOSTLY_BF16",
}


class _Reader:
    """Bounded little-endian reader over a binary file object."""

    def __init__(self, fh: Any, limit: int = 64 * 1024 * 1024):
        self._fh = fh
        self._limit = limit
        self._pos = 0

    def read(self, n: int) -> bytes:
        if self._pos + n > self._limit:
            raise GGUFError(
                f"header exceeds {self._limit} byte safety limit")
        data = self._fh.read(n)
        if len(data) != n:
            raise GGUFError(
                f"truncated file: wanted {n} bytes at offset "
                f"{self._pos}, got {len(data)}")
        self._pos += n
        return data

    def u8(self) -> int:
        return struct.unpack("<B", self.read(1))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def i8(self) -> int:
        return struct.unpack("<b", self.read(1))[0]

    def i16(self) -> int:
        return struct.unpack("<h", self.read(2))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def gguf_str(self) -> str:
        length = self.u64()
        if length > 10 * 1024 * 1024:
            raise GGUFError(f"string length {length} implausible")
        return self.read(length).decode("utf-8", errors="replace")


def _read_value(reader: _Reader, value_type: int) -> Any:
    if value_type == 0:
        return reader.u8()
    if value_type == 1:
        return reader.i8()
    if value_type == 2:
        return reader.u16()
    if value_type == 3:
        return reader.i16()
    if value_type == 4:
        return reader.u32()
    if value_type == 5:
        return reader.i32()
    if value_type == 6:
        return reader.f32()
    if value_type == 7:
        return reader.u8() != 0
    if value_type == 8:
        return reader.gguf_str()
    if value_type == 9:  # array
        elem_type = reader.u32()
        length = reader.u64()
        if length > 1_000_000:
            raise GGUFError(f"array length {length} implausible")
        return [_read_value(reader, elem_type) for _ in range(length)]
    if value_type == 10:
        return reader.u64()
    if value_type == 11:
        return reader.i64()
    if value_type == 12:
        return reader.f64()
    raise GGUFError(f"unknown GGUF value type {value_type}")


def parse_gguf_header(path: str | Path) -> dict[str, Any]:
    """Parse a GGUF header into its key/value metadata dict.

    Reads only the header — tensor blobs are never loaded. Raises
    :class:`GGUFError` for non-GGUF or corrupt files.
    """
    path = Path(path)
    metadata: dict[str, Any] = {}
    tensor_count = 0
    with open(path, "rb") as fh:
        reader = _Reader(fh)
        if reader.read(4) != GGUF_MAGIC:
            raise GGUFError(f"{path}: bad magic, not a GGUF file")
        version = reader.u32()
        if version != GGUF_VERSION:
            raise GGUFError(
                f"{path}: GGUF version {version}, parser targets "
                f"{GGUF_VERSION}")
        tensor_count = reader.u64()
        kv_count = reader.u64()
        if kv_count > 100_000:
            raise GGUFError(f"{path}: kv count {kv_count} implausible")
        for _ in range(kv_count):
            key = reader.gguf_str()
            value_type = reader.u32()
            metadata[key] = _read_value(reader, value_type)
        # Skip tensor infos (headers only, no blob data).
        for _ in range(tensor_count):
            reader.gguf_str()  # name
            n_dims = reader.u32()
            for _ in range(n_dims):
                reader.u64()  # dims
            reader.u32()  # dtype
            reader.u64()  # offset
    metadata["__tensor_count"] = tensor_count
    return metadata


@dataclass
class GGUFModel:
    """One discovered GGUF file with extracted metadata."""

    path: Path
    size_bytes: int
    architecture: str = "unknown"
    name: str = ""
    context_length: int = 0
    embedding_length: int = 0
    block_count: int = 0
    head_count: int = 0
    quantization: str = "unknown"
    tensor_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def display(self) -> str:
        base = self.name or self.path.name
        return f"{base} [{self.architecture}, {self.quantization}]"


def _extract(metadata: dict[str, Any], path: Path) -> GGUFModel:
    size = path.stat().st_size
    arch = str(metadata.get("general.architecture", "unknown"))
    name = str(metadata.get("general.name", path.stem))
    file_type = metadata.get("general.file_type")
    quantization = FILE_TYPES.get(file_type, f"file_type_{file_type}") \
        if isinstance(file_type, int) else "unknown"

    def _int(key: str) -> int:
        value = metadata.get(f"{arch}.{key}", metadata.get(key, 0))
        return int(value) if isinstance(value, (int, float)) else 0

    return GGUFModel(
        path=path,
        size_bytes=size,
        architecture=arch,
        name=name,
        context_length=_int("context_length"),
        embedding_length=_int("embedding_length"),
        block_count=_int("block_count"),
        head_count=_int("attention.head_count"),
        quantization=quantization,
        tensor_count=int(metadata.get("__tensor_count", 0)),
        metadata={k: v for k, v in metadata.items()
                  if not k.startswith("__")},
    )


def find_gguf_files(directories: list[str | Path],
                    recursive: bool = True) -> list[Path]:
    """All ``.gguf`` files under ``directories`` (sorted, deduped)."""
    found: list[Path] = []
    for directory in directories:
        root = Path(directory)
        if not root.is_dir():
            continue
        pattern = "**/*.gguf" if recursive else "*.gguf"
        found.extend(p for p in root.glob(pattern) if p.is_file())
    # Dedupe while keeping order, then sort for determinism.
    return sorted(set(found))


def discover_gguf_models(directories: list[str | Path],
                         recursive: bool = True) -> list[GGUFModel]:
    """Discover and parse every GGUF file under ``directories``.

    Corrupt files yield a :class:`GGUFModel` with ``error`` set —
    never an exception — so one bad file can't abort a scan.
    """
    models = []
    for path in find_gguf_files(directories, recursive):
        try:
            metadata = parse_gguf_header(path)
        except (GGUFError, OSError) as e:
            models.append(GGUFModel(
                path=path, size_bytes=_safe_size(path),
                error=f"{type(e).__name__}: {e}"))
            continue
        models.append(_extract(metadata, path))
    return models


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def gguf_model_size_human(size_bytes: int) -> str:
    """``123456789`` -> ``'117.7 MB'``."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"  # pragma: no cover - unreachable


# Re-exported for the metadata scanner (slice 161).
__all__ = [
    "GGUF_MAGIC",
    "GGUF_VERSION",
    "GGUFError",
    "GGUFModel",
    "discover_gguf_models",
    "find_gguf_files",
    "gguf_model_size_human",
    "parse_gguf_header",
]
