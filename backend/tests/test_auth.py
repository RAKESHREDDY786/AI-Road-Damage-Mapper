"""Verifies the optional API-key protection on data-changing endpoints.

`api_secure` runs a server with API_KEY=test-secret-key while `api` runs the
default server with protection disabled (local development).
"""


def test_writes_require_api_key_when_configured(api_secure):
    # Reads remain public.
    assert api_secure.get("/health")[0] == 200
    assert api_secure.get("/reports")[0] == 200

    # Writes are rejected without a key...
    assert api_secure.post_json("/reports", {"damage_type": "POTHOLE"})[0] == 401
    # ...and with the wrong key.
    assert api_secure.post_json(
        "/reports", {"damage_type": "POTHOLE"}, headers={"X-API-Key": "wrong"}
    )[0] == 401

    # With the correct key the write is allowed.
    status, body = api_secure.post_json(
        "/reports", {"damage_type": "POTHOLE"}, headers={"X-API-Key": "test-secret-key"}
    )
    assert status == 201
    report_id = body["id"]

    # DELETE is protected too.
    assert api_secure.delete("/reports/%d" % report_id)[0] == 401
    assert api_secure.delete(
        "/reports/%d" % report_id, headers={"X-API-Key": "test-secret-key"}
    )[0] == 200


def test_default_server_allows_unauthenticated_writes(api):
    status, body = api.post_json("/reports", {"damage_type": "POTHOLE"})
    assert status == 201
    api.delete("/reports/%d" % body["id"])