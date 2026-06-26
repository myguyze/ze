from ze_plugin.plugin import ZePlugin


class _EmptyPlugin(ZePlugin):
    pass


def test_rest_routes_default_empty():
    assert _EmptyPlugin().rest_routes() == []
