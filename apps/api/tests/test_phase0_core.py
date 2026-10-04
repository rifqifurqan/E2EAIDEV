import asyncio

from fastapi.testclient import TestClient

from e2eai.authz import Authz
from e2eai.core.ids import uuid7
from e2eai.main import create_app


class FailingClient:
    async def post(self, *args, **kwargs):
        raise RuntimeError("OpenFGA unavailable")


def test_health_endpoint():
    client = TestClient(create_app())
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_uuid7_has_version_variant_and_timestamp_prefix():
    ids = [uuid7() for _ in range(20)]
    assert all(i.version == 7 for i in ids)
    assert all((i.int >> 62) & 0b11 == 0b10 for i in ids)  # RFC 4122/RFC 9562 variant
    assert all((i.int >> 80) > 0 for i in ids)


def test_openfga_check_fails_closed_on_error():
    authz = Authz(FailingClient(), store_id="store", model_id="model")  # type: ignore[arg-type]
    assert asyncio.run(authz.check("user:andi", "viewer", "document:x")) is False
