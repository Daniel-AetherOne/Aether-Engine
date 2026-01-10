import os


def register_verticals(app):
    if os.getenv("ENABLE_PAINTERS_US", "0") == "1":
        from app.verticals.painters_us.adapter import PaintersUSAdapter

        PaintersUSAdapter().register(app)
