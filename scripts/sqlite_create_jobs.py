from app.db import Base, engine
from app.models.lead import Lead  # noqa
from app.models.job import Job  # noqa

Base.metadata.create_all(bind=engine)
print("created")