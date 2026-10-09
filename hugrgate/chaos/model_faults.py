"""Corrupt-model simulation. Slice 257.

A broken model file is one of the nastiest production failures: the
bytes are there, the loader starts, and then something is wrong.
:class:`ModelCorruptor` builds minimal *valid* GGUF files from scratch
(no model weights needed — headers only) and corrupts them in
scripted, seeded ways, so the loader's rejection behavior can be
attacked deterministically:

- ``flip_magic`` — magic bytes destroyed; must be rejected as
  "not a GGUF file";
- ``bad_version`` — version field rewritten; must be rejected;
- ``truncate`` — file cut at a seeded offset; the bounded reader
  must raise instead of returning short data;
- ``kv_bomb`` — key/value count inflated past the implausibility
  limit; must be rejected without allocating;
- ``zero_out`` — every byte zeroed;
- ``bit_flip`` — one seeded byte flipped. This one *may* survive
  parsing (a flipped padding byte is harmless); the asserted
  property is weaker but honest: parsing either succeeds or raises
  :class:`~hugrgate.errors.GGUFError` — never another exception
  type, never a hang.

Corruption never touches the original: :meth:`corrupt` writes a
sibling copy. Verification helpers assert the loader rejects the
corruption through both entry points — :func:`parse_gguf_header`
(raises) and :func:`discover_gguf_models` (records ``error``, never
aborts the scan).
"""

from __future__ import annotations

import random
import struct
from pathlib import Path

from hugrgate.errors import GGUFError, SpecError
from hugrgate.runtimes.gguf import (
    GGUF_MAGIC,
    GGUF_VERSION,
    discover_gguf_models,
    parse_gguf_header,
)

__all__ = [
    "CORRUPTION_KINDS",
    "MUST_REJECT_KINDS",
    "ModelCorruptor",
]

#: All corruption kinds :meth:`ModelCorruptor.corrupt` understands.
CORRUPTION_KINDS = (
    "flip_magic",
    "bad_version",
    "truncate",
    "kv_bomb",
    "zero_out",
    "bit_flip",
)

#: Kinds that must make the loader raise GGUFError. ``bit_flip`` is
#: deliberately excluded: a flipped padding byte may parse fine.
MUST_REJECT_KINDS = frozenset(
    {"flip_magic", "bad_version", "truncate", "kv_bomb", "zero_out"})


def _gguf_str(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


class ModelCorruptor:
    """Build valid GGUF files and corrupt copies of them."""

    def __init__(self, seed: int | None = None):
        self._seed = seed

    # --- valid file construction -------------------------------------------
    @staticmethod
    def write_valid(path: str | Path, *,
                    architecture: str = "llama",
                    tensor_count: int = 0) -> Path:
        """Write a minimal *valid* GGUF file: magic, version, one
        string kv pair, no tensors. Headers only — no weights."""
        path = Path(path)
        if tensor_count < 0:
            raise SpecError(
                f"tensor_count must be >= 0, got {tensor_count}")
        blob = bytearray()
        blob += GGUF_MAGIC
        blob += struct.pack("<I", GGUF_VERSION)
        blob += struct.pack("<Q", tensor_count)
        blob += struct.pack("<Q", 1)  # one kv pair
        blob += _gguf_str("general.architecture")
        blob += struct.pack("<I", 8)  # string value type
        blob += _gguf_str(architecture)
        path.write_bytes(bytes(blob))
        return path

    # --- corruption ----------------------------------------------------------
    def corrupt(self, path: str | Path, kind: str,
                seed: int | None = None) -> Path:
        """Write a corrupted sibling copy of ``path``.

        The copy is named ``<stem>.corrupt-<kind>.gguf`` so discovery
        still finds it. ``seed`` overrides this corruptor's seed for
        this call. The original file is never modified.
        """
        if kind not in CORRUPTION_KINDS:
            raise SpecError(
                f"unknown corruption kind {kind!r}; "
                f"expected one of {list(CORRUPTION_KINDS)}")
        src = Path(path)
        original = src.read_bytes()
        rng = random.Random(self._seed if seed is None else seed)
        corrupted = self._apply(kind, original, rng)
        dest = src.with_name(f"{src.stem}.corrupt-{kind}.gguf")
        dest.write_bytes(corrupted)
        return dest

    @staticmethod
    def _apply(kind: str, original: bytes, rng: random.Random) -> bytes:
        data = bytearray(original)
        if kind == "flip_magic":
            data[0:4] = b"GGUH"
        elif kind == "bad_version":
            struct.pack_into("<I", data, 4, 99)
        elif kind == "truncate":
            # Keep at least the magic so the failure is truncation,
            # not a magic mismatch; cut before the header completes.
            cut = rng.randint(4, max(4, len(data) - 1))
            data = data[:cut]
        elif kind == "kv_bomb":
            # kv_count lives at offset 16 (4 magic + 4 version + 8 tensors).
            struct.pack_into("<Q", data, 16, 200_000)
        elif kind == "zero_out":
            data = bytearray(len(data))
        elif kind == "bit_flip":
            offset = rng.randrange(len(data))
            data[offset] ^= 1 << rng.randrange(8)
        return bytes(data)

    # --- verification ----------------------------------------------------------
    @staticmethod
    def assert_rejected(path: str | Path) -> GGUFError:
        """Assert :func:`parse_gguf_header` rejects the file with
        :class:`GGUFError`. Returns the error for message assertions."""
        try:
            parse_gguf_header(path)
        except GGUFError as e:
            return e
        raise AssertionError(
            f"corrupt model {path} was NOT rejected by the loader")

    @staticmethod
    def assert_scan_survives(directory: str | Path) -> list:
        """Assert :func:`discover_gguf_models` never aborts on a
        directory of corrupt files. Returns the discovered models."""
        return discover_gguf_models([directory])
