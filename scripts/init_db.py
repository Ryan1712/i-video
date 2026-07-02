"""Create all DB tables. Run once after first deploy, before starting the API."""
from saas.db import Base, init_session_factory

engine = init_session_factory().kw["bind"]
Base.metadata.create_all(engine)
print("Database tables created.")
