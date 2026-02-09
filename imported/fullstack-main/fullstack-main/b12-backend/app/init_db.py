from app.core.database import engine
from app.core.db_models import Base

Base.metadata.create_all(bind=engine)
print("Clinical database initialized.")
