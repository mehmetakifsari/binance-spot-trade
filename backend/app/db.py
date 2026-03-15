from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings

DATABASE_URL = (
    f"postgresql+psycopg2://{settings.db_user}:{settings.db_password}@"
    f"{settings.db_host}:{settings.db_port}/{settings.db_name}"
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
