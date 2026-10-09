"""Slice 427 — OpenAPI stabilization.

The generated OpenAPI schema is a contract: every route is tagged
and summarized, the ``/decide`` envelope is validated against a
documented Pydantic model before domain parsing, malformed requests
get structured 422s (never accidental 500s), and ``hugrgate
openapi`` dumps the schema from the live route table so it cannot
drift from the implementation.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from hugrgate import __version__ as HUGRGATE_VERSION
from hugrgate.protocol import PROTOCOL_VERSION
from hugrgate.server import (
    DecideRequest,
    create_app,
    dump_openapi_schema,
)


@pytest.fixture()
def schema():
    return dump_openapi_schema()


def test_schema_info_matches_package(schema):
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "HugrGate"
    assert schema["info"]["version"] == HUGRGATE_VERSION


@pytest.mark.parametrize("path", ["/", "/health", "/backends", "/models",
                                   "/decide", "/protocol"])
def test_all_routes_present(schema, path):
    assert path in schema["paths"], f"missing route in schema: {path}"


def test_every_operation_is_tagged_and_summarized(schema):
    for path, ops in schema["paths"].items():
        for method, op in ops.items():
            assert op.get("tags"), f"{method} {path} has no tags"
            assert op.get("summary"), f"{method} {path} has no summary"


def test_decide_request_schema_requires_spec_and_state(schema):
    decide = schema["paths"]["/decide"]["post"]
    body = decide["requestBody"]["content"]["application/json"]["schema"]
    assert "$ref" in body  # documented via DecideRequest model
    comp = schema["components"]["schemas"]["DecideRequest"]
    assert set(comp["required"]) >= {"spec", "state"}
    props = comp["properties"]
    assert "protocol_version" in props
    assert props["protocol_version"]["description"]


def test_decide_error_responses_documented(schema):
    responses = schema["paths"]["/decide"]["post"]["responses"]
    for status in ("400", "422", "502", "503"):
        assert status in responses, f"/decide missing {status} docs"


def test_protocol_response_model_documented(schema):
    comp = schema["components"]["schemas"]["ProtocolBody"]
    assert set(comp["required"]) >= {"protocol_version",
                                    "supported_versions", "service_version"}


def test_schema_is_json_serializable(schema):
    json.dumps(schema)  # must not raise


def test_malformed_envelope_gets_structured_422():
    client = TestClient(create_app())
    # missing required "spec"
    resp = client.post("/decide", json={"state": {}})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "bad_request"
    assert "spec" in err["message"]


def test_non_object_body_gets_400():
    client = TestClient(create_app())
    resp = client.post("/decide", json=[1, 2, 3])
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_wrong_type_field_gets_structured_422():
    client = TestClient(create_app())
    resp = client.post("/decide", json={"spec": {"type": "categorical",
                                                 "options": ["a", "b"]},
                                        "state": "not-a-dict"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "bad_request"


def test_decide_request_model_validates():
    req = DecideRequest.model_validate(
        {"protocol_version": PROTOCOL_VERSION,
         "spec": {"type": "categorical", "options": ["a", "b"]},
         "state": {"f": 1.0}})
    assert req.protocol_version == PROTOCOL_VERSION
    assert req.state == {"f": 1.0}
    assert req.backend_name is None


def test_decide_request_model_rejects_missing_state():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DecideRequest.model_validate({"spec": {}})


def test_cli_openapi_writes_schema_file(tmp_path):
    from hugrgate.cli import main
    out = tmp_path / "openapi.json"
    assert main(["openapi", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert data["info"]["title"] == "HugrGate"
    assert "/decide" in data["paths"]
