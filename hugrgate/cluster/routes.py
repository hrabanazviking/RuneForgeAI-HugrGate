"""Cluster HTTP routes — ``/cluster/*``. Slice 207.

The router is built bound to a :class:`ClusterNode`
(:func:`build_cluster_router`) and mounted by ``create_app`` /
``create_daemon_app`` only when a node is supplied, so the standalone
server is untouched.

Routes (all localhost-scoped like the rest of the API):

- ``POST /cluster/rpc`` — the envelope endpoint: decodes the
  :class:`ClusterMessage`, runs ``node.dispatch``, returns the reply
  envelope. Undecodable bodies are HTTP 400; application outcomes
  (including typed errors) are HTTP 200 envelopes.
- ``GET /cluster/peers`` — the node's current peer table.
- ``GET /cluster/health`` — node identity, capabilities summary, and
  peer count (liveness for load balancers).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRouter

from hugrgate.cluster.protocol import (
    CLUSTER_RPC_PATH,
    ClusterMessage,
    decode_message,
)
from hugrgate.errors import SpecError

if TYPE_CHECKING:
    from hugrgate.cluster.node import ClusterNode

__all__ = [
    "build_cluster_router",
]


def build_cluster_router(node: ClusterNode) -> APIRouter:
    """Build the ``/cluster/*`` router bound to ``node``."""
    router = APIRouter()

    @router.post(CLUSTER_RPC_PATH)
    async def cluster_rpc(request: Request) -> JSONResponse:
        try:
            body = await request.body()
            message = decode_message(body)
        except SpecError as e:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "spec_error",
                                  "message": str(e),
                                  "recoverable": False,
                                  "details": {}}})
        # Mutual authentication (slice 208): the tag covers the exact
        # wire bytes; the node verifies before dispatching.
        tag = request.headers.get("x-cluster-mac")
        reply: ClusterMessage = node.dispatch(message, auth_tag=tag,
                                              raw=body)
        return JSONResponse(
            status_code=200,
            content={"envelope": reply.to_dict()})

    @router.get("/cluster/peers")
    def cluster_peers() -> list[dict[str, Any]]:
        return [peer.to_dict() for peer in node.peers()]

    @router.get("/cluster/health")
    def cluster_health() -> dict[str, Any]:
        caps = node.capabilities()
        return {
            "status": "ok",
            "node_id": node.node_id,
            "display_name": node.identity.display_name,
            "backends": caps.backend_names(),
            "spec_types": caps.spec_types(),
            "peers": len(node.peers()),
            "serve_remote": node.serve_remote,
        }

    return router
