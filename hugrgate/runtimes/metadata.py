"""Model metadata scanner. Slice 161.

:func:`scan_directory` walks directories for model artifacts in every
format the fabric understands and :func:`scan_model` extracts a
:class:`ModelMetadata` record from each one:

- ``.gguf`` → the pure-python header parser from
  :mod:`hugrgate.runtimes.gguf` (architecture, context length,
  quantization, parameter *estimate* from size x bits-per-weight);
- ``.safetensors`` → the JSON header: ``__metadata__`` plus an exact
  parameter count summed over tensor shapes (never estimated);
- ``.onnx`` → shallow scan (path/format/size) unless the ``onnx``
  package is importable, in which case producer + graph IO are read;
- Hugging Face repo directories (``config.json`` present) →
  ``architectures``, ``model_type``, hidden size / layers / context
  window, tokenizer class, and ``README.md`` frontmatter (license,
  tags, languages, pipeline tag).

Estimates are always labeled as estimates; unknown fields stay
``""``/``0``/``None`` instead of being guessed. Corrupt files yield
``error`` rather than raising.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hugrgate.runtimes import format_from_path
from hugrgate.runtimes.gguf import GGUFError, parse_gguf_header

__all__ = [
    "MODEL_SUFFIXES",
    "ModelMetadata",
    "scan_directory",
    "scan_model",
]

#: File suffixes treated as model artifacts (plus HF repo dirs).
MODEL_SUFFIXES = (".gguf", ".onnx", ".safetensors", ".bin", ".pt",
                  ".pth", ".engine", ".plan", ".xml")

#: GGUF quantization label -> approximate bits per weight (for the
#: parameter *estimate*; embedding/output layers add overhead, so this
#: is deliberately labeled an estimate).
_QUANT_BITS = {
    "ALL_F32": 32.0, "MOSTLY_BF16": 16.0, "MOSTLY_F16": 16.0,
    "MOSTLY_Q8_0": 8.5, "MOSTLY_Q6_K": 6.6, "MOSTLY_Q5_K_M": 5.7,
    "MOSTLY_Q5_K_S": 5.6, "MOSTLY_Q5_1": 5.5, "MOSTLY_Q5_0": 5.5,
    "MOSTLY_Q4_K_M": 4.9, "MOSTLY_Q4_K_S": 4.8, "MOSTLY_Q4_1": 4.5,
    "MOSTLY_Q4_0": 4.5, "MOSTLY_Q3_K_L": 3.9, "MOSTLY_Q3_K_M": 3.8,
    "MOSTLY_Q3_K_S": 3.7, "MOSTLY_Q2_K": 3.4, "MOSTLY_Q2_K_S": 3.3,
}


@dataclass
class ModelMetadata:
    """One scanned model artifact."""

    path: Path
    format: str
    size_bytes: int
    architecture: str = "unknown"
    name: str = ""
    context_length: int = 0
    parameters: int = 0  # exact when known, else 0
    parameters_estimate: float = 0.0  # always labeled an estimate
    quantization: str = "unknown"
    license: str = ""
    source: str = ""  # e.g. HF repo id when known
    tokenizer: str = ""
    languages: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    scan_depth: str = "full"  # "full" | "shallow"
    extra: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def parameters_human(self) -> str:
        n = self.parameters or self.parameters_estimate
        if n >= 1e9:
            return f"{n / 1e9:.1f}B"
        if n >= 1e6:
            return f"{n / 1e6:.1f}M"
        if n >= 1e3:
            return f"{n / 1e3:.1f}K"
        return f"{int(n)}"


def _base(path: Path, scan_depth: str = "full") -> ModelMetadata:
    return ModelMetadata(
        path=path, format=format_from_path(path),
        size_bytes=_safe_size(path), name=path.stem,
        scan_depth=scan_depth)


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


# -- GGUF ------------------------------------------------------------------------


def _scan_gguf(path: Path) -> ModelMetadata:
    meta = _base(path)
    try:
        kv = parse_gguf_header(path)
    except (GGUFError, OSError) as e:
        meta.error = f"{type(e).__name__}: {e}"
        return meta
    arch = str(kv.get("general.architecture", "unknown"))
    meta.architecture = arch
    meta.name = str(kv.get("general.name", path.stem))

    def _int(key: str) -> int:
        value = kv.get(f"{arch}.{key}", kv.get(key, 0))
        return int(value) if isinstance(value, (int, float)) else 0

    meta.context_length = _int("context_length")
    file_type = kv.get("general.file_type")
    from hugrgate.runtimes.gguf import FILE_TYPES
    meta.quantization = FILE_TYPES.get(file_type, "unknown") \
        if isinstance(file_type, int) else "unknown"
    bits = _QUANT_BITS.get(meta.quantization)
    if bits:
        # Rough: weights dominate the file; metadata/vocab overhead
        # means this slightly *under*-counts — labeled an estimate.
        meta.parameters_estimate = meta.size_bytes * 8.0 / bits * 0.94
    meta.extra["gguf_keys"] = sorted(k for k in kv
                                     if not k.startswith("__"))
    return meta


# -- safetensors --------------------------------------------------------------------


def _scan_safetensors(path: Path) -> ModelMetadata:
    meta = _base(path)
    try:
        with open(path, "rb") as fh:
            header_len = struct.unpack("<Q", fh.read(8))[0]
            if header_len > 100 * 1024 * 1024:
                raise ValueError(
                    f"safetensors header {header_len} bytes implausible")
            header = json.loads(fh.read(header_len).decode("utf-8"))
    except (OSError, ValueError, struct.error,
            UnicodeDecodeError, json.JSONDecodeError) as e:
        meta.error = f"{type(e).__name__}: {e}"
        return meta
    info = header.get("__metadata__", {}) or {}
    total = 0
    for tensor_name, spec in header.items():
        if tensor_name == "__metadata__":
            continue
        shape = spec.get("shape", [])
        count = 1
        for dim in shape:
            count *= int(dim)
        total += count
    meta.parameters = total
    meta.architecture = str(
        info.get("architecture", info.get("model_type", "unknown")))
    for key in ("format", "quantization"):
        if info.get(key):
            meta.quantization = str(info[key])
    return meta


# -- ONNX -----------------------------------------------------------------------------


def _scan_onnx(path: Path) -> ModelMetadata:
    meta = _base(path)
    try:
        import onnx  # noqa: F401
    except Exception:  # noqa: BLE001 - shallow scan without the package
        meta.scan_depth = "shallow"
        meta.extra["note"] = ("onnx package not installed; install "
                              "'hugrgate[onnx]' for producer/graph IO")
        return meta
    try:
        import onnx as onnx_pkg
        model = onnx_pkg.load(str(path), load_external_data=False)
    except Exception as e:  # noqa: BLE001 - corrupt file -> error field
        meta.error = f"{type(e).__name__}: {e}"
        return meta
    meta.extra["producer"] = str(model.producer_name or "")
    meta.extra["doc_string"] = str(model.doc_string or "")[:500]
    graph = model.graph
    meta.extra["inputs"] = [i.name for i in graph.input]
    meta.extra["outputs"] = [o.name for o in graph.output]
    meta.extra["node_count"] = len(graph.node)
    return meta


# -- Hugging Face repos ------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _read_frontmatter(readme: Path) -> dict[str, Any]:
    try:
        text = readme.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    front: dict[str, Any] = {}
    for line in text[3:end].splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        front[key.strip()] = value.strip().strip("'\"")
    # naive list parse for `tags: [a, b]`
    for key, value in list(front.items()):
        if isinstance(value, str) and value.startswith("["):
            front[key] = [v.strip().strip("'\"")
                          for v in value.strip("[]").split(",")
                          if v.strip()]
    return front


def _scan_hf_repo(path: Path) -> ModelMetadata:
    meta = _base(path)
    meta.format = "hf"
    config = _read_json(path / "config.json")
    if config is None:
        meta.scan_depth = "shallow"
        meta.extra["note"] = "no config.json; directory scan only"
        return meta
    archs = config.get("architectures") or []
    meta.architecture = str(
        config.get("model_type")
        or (archs[0] if archs else "unknown"))
    meta.name = path.name
    meta.context_length = int(config.get("max_position_embeddings")
                              or config.get("n_positions") or 0)
    meta.extra["hidden_size"] = config.get("hidden_size")
    meta.extra["num_layers"] = (config.get("num_hidden_layers")
                                or config.get("n_layer"))
    tok_config = _read_json(path / "tokenizer_config.json")
    if tok_config:
        meta.tokenizer = str(tok_config.get("tokenizer_class", ""))
    for readme_name in ("README.md", "readme.md"):
        front = _read_frontmatter(path / readme_name)
        if front:
            break
    else:
        front = {}
    if front.get("license"):
        meta.license = str(front["license"])
    tags = front.get("tags", [])
    meta.tags = [str(t) for t in tags] if isinstance(tags, list) \
        else [str(tags)]
    langs = front.get("language", [])
    meta.languages = [str(lang) for lang in langs] \
        if isinstance(langs, list) \
        else ([str(langs)] if langs else [])
    if front.get("pipeline_tag"):
        meta.extra["pipeline_tag"] = str(front["pipeline_tag"])
    return meta


# -- dispatch -------------------------------------------------------------------------------


def _is_hf_repo(path: Path) -> bool:
    """A directory is an HF repo when it carries a config.json."""
    return path.is_dir() and (path / "config.json").is_file()


def scan_model(path: str | Path) -> ModelMetadata:
    """Scan one model file or HF repo directory."""
    path = Path(path)
    if _is_hf_repo(path):
        return _scan_hf_repo(path)
    suffix = path.suffix.lower()
    if suffix == ".gguf":
        return _scan_gguf(path)
    if suffix == ".safetensors":
        return _scan_safetensors(path)
    if suffix == ".onnx":
        return _scan_onnx(path)
    meta = _base(path, scan_depth="shallow")
    if suffix not in MODEL_SUFFIXES:
        meta.error = f"unsupported suffix {suffix!r}"
    else:
        meta.extra["note"] = ("shallow scan: size/format only; no "
                              "header parser for this format")
    return meta


def scan_directory(directories: list[str | Path],
                   recursive: bool = True) -> list[ModelMetadata]:
    """Scan directories for model artifacts (files + HF repos)."""
    found: list[Path] = []
    for directory in directories:
        root = Path(directory)
        if not root.is_dir():
            continue
        pattern = "**/*" if recursive else "*"
        for path in root.glob(pattern):
            if path.is_file() and path.suffix.lower() in MODEL_SUFFIXES:
                found.append(path)
            elif _is_hf_repo(path):
                found.append(path)
    # Exclude files *inside* discovered HF repos (they belong to the
    # repo record, not to standalone scans).
    repos = {p for p in found if _is_hf_repo(p)}
    standalone = [p for p in found
                  if not any(r in p.parents for r in repos)]
    return [scan_model(p) for p in sorted(set(standalone))]
