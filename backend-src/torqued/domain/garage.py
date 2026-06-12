from dataclasses import dataclass


@dataclass
class Garage:
    id: int
    name: str
    created_at: str | None = None
