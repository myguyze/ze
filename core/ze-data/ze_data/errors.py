from __future__ import annotations


class SchemaMismatchError(Exception):
    def __init__(self, archive: list[str], current: list[str]) -> None:
        self.archive = archive
        self.current = current
        super().__init__(
            f"Archive schema revisions {sorted(archive)} do not match "
            f"current revisions {sorted(current)}. "
            "Ensure you are importing an archive created by the same Ze version."
        )


class InstanceNotEmptyError(Exception):
    pass
