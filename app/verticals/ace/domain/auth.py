from dataclasses import dataclass

@dataclass(frozen=True)
class AdminIdentity:
    username: str
    auth_method: str = "basic"
