from e2eai.main import create_app


def test_documents_list_endpoint_is_exposed_for_uat_reload_and_tabs():
    paths = create_app().openapi()["paths"]
    assert "get" in paths["/api/v1/documents"]
