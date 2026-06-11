from __future__ import annotations

from ze_core.errors import InterfaceConfigError
from ze_core.interface.base import AppInterface

_VALID_STYLES = ("inline", "async")


def validate_interface(iface: object) -> None:
    """
    Validate that an interface object satisfies the AppInterface contract.
    Raises InterfaceConfigError on any violation. Called by the container at startup.
    """
    style = getattr(type(iface), "confirmation_style", None)

    if style is None:
        raise InterfaceConfigError(
            f"{type(iface).__name__} must define a `confirmation_style` class variable"
        )

    if style not in _VALID_STYLES:
        raise InterfaceConfigError(
            f"{type(iface).__name__}.confirmation_style must be 'inline' or 'async', got {style!r}"
        )

    if style == "inline":
        confirm = getattr(type(iface), "confirm", None)
        if confirm is None or confirm is AppInterface.confirm:
            raise InterfaceConfigError(
                f"{type(iface).__name__} declares confirmation_style='inline' "
                "but does not override confirm()"
            )

    if style == "async":
        send_confirmation = getattr(type(iface), "send_confirmation", None)
        if send_confirmation is None or send_confirmation is AppInterface.send_confirmation:
            raise InterfaceConfigError(
                f"{type(iface).__name__} declares confirmation_style='async' "
                "but does not override send_confirmation()"
            )
