"""Tests for OpenAPI export including plugin routes."""

from ze_api.openapi_export import (
    collect_openapi_operation_ids,
    collect_static_plugin_routers,
    export_openapi,
)


def test_collect_static_plugin_routers_includes_news():
    routers = collect_static_plugin_routers()
    paths = [route.path for router in routers for route in router.routes]
    assert "/api/v0/news/page" in paths
    assert "/api/v0/news/settings" in paths
    assert "/api/v0/contacts/page" in paths
    assert "/api/v0/reminders/page" in paths


def test_export_openapi_includes_ui_manifest():
    schema = export_openapi()
    assert "/api/v0/ui/manifest" in schema["paths"]
    assert (
        "getUiManifest" in schema["paths"]["/api/v0/ui/manifest"]["get"]["operationId"]
    )


def test_collect_openapi_operation_ids_includes_plugin_pages():
    operation_ids = collect_openapi_operation_ids()
    assert "getNewsPage" in operation_ids
    assert "getNewsSettings" in operation_ids
    assert "getContactsPage" in operation_ids
    assert "getRemindersPage" in operation_ids
