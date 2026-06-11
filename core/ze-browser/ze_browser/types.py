from dataclasses import dataclass


@dataclass
class BrowserResult:
    url: str
    title: str
    text: str
    status_code: int
