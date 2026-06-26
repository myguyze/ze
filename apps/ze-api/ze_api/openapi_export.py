"""OpenAPI export with plugin REST routes included (for codegen)."""

from __future__ import annotations

import importlib
import json

from ze_plugin.bootstrap import load_plugin_classes


def collect_static_plugin_routers() -> list:
    """Import plugin route modules without instantiating plugins."""
    routers: list = []
    for _name, cls in load_plugin_classes():
        pkg = cls.__module__.rsplit(".", 1)[0]
        try:
            mod = importlib.import_module(f"{pkg}.api.routes")
        except ModuleNotFoundError:
            continue
        router = getattr(mod, "router", None)
        if router is not None:
            routers.append(router)
    return routers


def collect_openapi_operation_ids() -> frozenset[str]:
    """Return all operationId values from the exported OpenAPI schema."""
    schema = export_openapi()
    ids: set[str] = set()
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                op_id = operation.get("operationId")
                if op_id:
                    ids.add(op_id)
    return frozenset(ids)


def export_openapi() -> dict:
    from ze_api.api.app import create_app

    app = create_app()
    for router in collect_static_plugin_routers():
        app.include_router(router)
    return app.openapi()


def main() -> None:
    print(json.dumps(export_openapi()))


if __name__ == "__main__":
    main()
