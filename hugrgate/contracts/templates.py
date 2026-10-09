"""Contract templates — reusable parameterized contracts.

Gjallarbrú slice 046.

Every deployment writes its fraud contract by hand, copying outcomes and
cost shapes and hoping the amounts are right. :class:`ContractTemplate`
captures the shape once, with ``${param}`` placeholders, and
:meth:`instantiate` fills them with validated parameters:

- :class:`TemplateParameter`: ``type`` (``string`` | ``number`` |
  ``integer`` | ``boolean`` | ``array`` | ``object`` | ``any``),
  ``required``, ``default``, and optional ``allowed`` values;
- substitution is recursive over the body dict: a string that is exactly
  ``${name}`` injects the raw value (numbers, lists, dicts survive);
  ``${name}`` inside a larger string interpolates textually;
- strictness both ways: undeclared placeholders are rejected at template
  construction; unknown parameters are rejected at instantiation;
- :class:`TemplateLibrary`: a named registry of templates.

The instantiated dict goes through :func:`contract_from_dict`, so the
result is a fully validated v2 contract, never a half-substituted dict.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from hugrgate.contracts.schema import (
    DecisionContract,
    contract_from_dict,
)
from hugrgate.errors import ContractError

__all__ = [
    "TEMPLATE_PARAM_TYPES",
    "ContractTemplate",
    "TemplateLibrary",
    "TemplateParameter",
]

#: Types a template parameter may declare.
TEMPLATE_PARAM_TYPES = (
    "string", "number", "integer", "boolean", "array", "object", "any",
)

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_FULL_PLACEHOLDER = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _type_ok(declared: str, value: Any) -> bool:
    if declared == "any":
        return True
    if declared == "string":
        return isinstance(value, str)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if declared == "array":
        return isinstance(value, (list, tuple))
    if declared == "object":
        return isinstance(value, Mapping)
    return False  # pragma: no cover - guarded by constructor


def find_placeholders(node: Any) -> list[str]:
    """Every ``${name}`` placeholder in a body, in order of appearance."""
    found: list[str] = []

    def walk(n: Any) -> None:
        if isinstance(n, str):
            found.extend(_PLACEHOLDER.findall(n))
        elif isinstance(n, Mapping):
            for k, v in n.items():
                walk(k)
                walk(v)
        elif isinstance(n, (list, tuple)):
            for v in n:
                walk(v)

    walk(node)
    return found


def _substitute(node: Any, params: Mapping[str, Any]) -> Any:
    if isinstance(node, str):
        full = _FULL_PLACEHOLDER.match(node)
        if full:
            return params[full.group(1)]
        def repl(m: re.Match[str]) -> str:
            return str(params[m.group(1)])
        return _PLACEHOLDER.sub(repl, node)
    if isinstance(node, Mapping):
        return {k: _substitute(v, params) for k, v in node.items()}
    if isinstance(node, list):
        return [_substitute(v, params) for v in node]
    if isinstance(node, tuple):
        return tuple(_substitute(v, params) for v in node)
    return node


@dataclass(frozen=True)
class TemplateParameter:
    """One declared template parameter."""

    type: str = "any"
    required: bool = True
    default: Any = None
    allowed: tuple[Any, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        if self.type not in TEMPLATE_PARAM_TYPES:
            raise ContractError(
                f"unknown template parameter type {self.type!r}",
                code="bad_template_parameter")
        if not isinstance(self.required, bool):
            raise ContractError("'required' must be a bool",
                                code="bad_template_parameter")
        if self.allowed:
            for v in self.allowed:
                if not _type_ok(self.type, v):
                    raise ContractError(
                        f"allowed value {v!r} does not match type "
                        f"{self.type!r}", code="bad_template_parameter")
        if not self.required and self.default is not None:
            if not _type_ok(self.type, self.default):
                raise ContractError(
                    f"default {self.default!r} does not match type "
                    f"{self.type!r}", code="bad_template_parameter")
            if self.allowed and self.default not in self.allowed:
                raise ContractError(
                    f"default {self.default!r} not in allowed values",
                    code="bad_template_parameter")

    def check(self, value: Any) -> str | None:
        """Violation message for one provided value, or None."""
        if not _type_ok(self.type, value):
            return (f"parameter must be {self.type}, got "
                    f"{type(value).__name__}")
        if self.allowed and value not in self.allowed:
            return (f"parameter value {value!r} not in allowed "
                    f"{list(self.allowed)}")
        return None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        if not self.required:
            d["required"] = False
        if self.default is not None:
            d["default"] = self.default
        if self.allowed:
            d["allowed"] = list(self.allowed)
        if self.description:
            d["description"] = self.description
        return d

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> TemplateParameter:
        if not isinstance(d, Mapping):
            raise ContractError("template parameter must be a mapping",
                                code="bad_template_parameter")
        return cls(type=d.get("type", "any"),
                   required=d.get("required", True),
                   default=d.get("default"),
                   allowed=tuple(d.get("allowed", ())),
                   description=d.get("description", ""))


@dataclass
class ContractTemplate:
    """A parameterized contract body ready to instantiate."""

    template_id: str
    body: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, TemplateParameter] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.template_id, str) or not self.template_id:
            raise ContractError("template_id must be a non-empty string",
                                code="bad_template")
        if not isinstance(self.body, dict) or not self.body:
            raise ContractError("template body must be a non-empty dict",
                                code="bad_template")
        if not isinstance(self.parameters, dict):
            raise ContractError("'parameters' must be a dict",
                                code="bad_template")
        for name, p in self.parameters.items():
            if not isinstance(name, str) or not name:
                raise ContractError("parameter names must be non-empty "
                                    "strings", code="bad_template")
            if not isinstance(p, TemplateParameter):
                raise ContractError(
                    f"parameter {name!r} must be a TemplateParameter",
                    code="bad_template")
        placeholders = find_placeholders(self.body)
        undeclared = [ph for ph in placeholders
                      if ph not in self.parameters]
        if undeclared:
            raise ContractError(
                f"template placeholders without declared parameters: "
                f"{sorted(set(undeclared))}", code="undeclared_placeholder")
        dangling = [ph for ph in set(placeholders)
                    if not self.parameters[ph].required
                    and self.parameters[ph].default is None]
        if dangling:
            raise ContractError(
                f"template placeholders for optional parameters without "
                f"defaults can never be filled: {sorted(dangling)}",
                code="dangling_placeholder")

    @property
    def parameter_names(self) -> list[str]:
        """Declared parameter names."""
        return list(self.parameters)

    def instantiate(self, **params: Any) -> DecisionContract:
        """Fill parameters and return a validated v2 contract."""
        unknown = [k for k in params if k not in self.parameters]
        if unknown:
            raise ContractError(
                f"unknown template parameters: {unknown}; declared: "
                f"{self.parameter_names}", code="unknown_template_parameter")
        filled: dict[str, Any] = {}
        for name, spec in self.parameters.items():
            if name in params:
                msg = spec.check(params[name])
                if msg is not None:
                    raise ContractError(
                        f"template parameter {name!r}: {msg}",
                        code="bad_template_argument")
                filled[name] = params[name]
            elif spec.required:
                raise ContractError(
                    f"missing required template parameter: {name!r}",
                    code="missing_template_parameter")
            elif spec.default is not None:
                filled[name] = spec.default
            else:
                # Optional without default: leave the placeholder — the
                # body must not require it.
                pass
        body = _substitute(self.body, filled)
        leftover = find_placeholders(body)
        if leftover:
            raise ContractError(
                f"unfilled placeholders after substitution: "
                f"{sorted(set(leftover))} (optional parameters without "
                f"defaults must not be referenced)",
                code="unfilled_placeholder")
        try:
            return contract_from_dict(body)
        except ContractError as e:
            raise ContractError(
                f"instantiated template is not a valid contract: "
                f"{e.message}", code="bad_template_body") from None

    def to_dict(self) -> dict[str, Any]:
        return {"template_id": self.template_id,
                "description": self.description,
                "parameters": {k: v.to_dict()
                               for k, v in self.parameters.items()},
                "body": self.body}

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> ContractTemplate:
        if not isinstance(d, Mapping):
            raise ContractError("template must be a mapping",
                                code="bad_template")
        try:
            return cls(
                template_id=d["template_id"],
                body=dict(d["body"]),
                parameters={k: TemplateParameter.from_dict(v)
                            for k, v in d.get("parameters", {}).items()},
                description=d.get("description", ""))
        except KeyError as e:
            raise ContractError(f"template missing key: {e}",
                                code="bad_template") from None


class TemplateLibrary:
    """A named registry of contract templates."""

    __slots__ = ("_templates",)

    def __init__(self) -> None:
        self._templates: dict[str, ContractTemplate] = {}

    def register(self, template: ContractTemplate) -> None:
        """Add a template; duplicate ids are rejected."""
        if not isinstance(template, ContractTemplate):
            raise ContractError("library holds ContractTemplates, got "
                                f"{type(template).__name__}",
                                code="bad_template")
        if template.template_id in self._templates:
            raise ContractError(
                f"template {template.template_id!r} already registered",
                code="duplicate_template")
        self._templates[template.template_id] = template

    def get(self, template_id: str) -> ContractTemplate:
        """Fetch a template by id."""
        try:
            return self._templates[template_id]
        except KeyError:
            raise ContractError(
                f"unknown template: {template_id!r}; known: "
                f"{sorted(self._templates)}",
                code="unknown_template") from None

    def __contains__(self, template_id: object) -> bool:
        return template_id in self._templates

    def __len__(self) -> int:
        return len(self._templates)

    def template_ids(self) -> list[str]:
        """Registered template ids in registration order."""
        return list(self._templates)

    def instantiate(self, template_id: str, **params: Any
                    ) -> DecisionContract:
        """Instantiate a registered template in one call."""
        return self.get(template_id).instantiate(**params)
