def test_public_api_imports() -> None:
    from ze_communication.channel import Channel
    from ze_communication.registry import ChannelRegistry
    from ze_data.domain import DataDomain
    from ze_plugin.plugin import ZePlugin
    from ze_plugin.signals import SignalSource

    assert ZePlugin is not None
    assert DataDomain is not None
    assert Channel is not None
    assert ChannelRegistry is not None
    assert SignalSource is not None
