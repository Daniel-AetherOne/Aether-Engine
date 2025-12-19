from app.verticals.registry import register
from app.verticals.painters_us.adapter import PaintersUSAdapter

def register_verticals() -> None:
    register(PaintersUSAdapter())
