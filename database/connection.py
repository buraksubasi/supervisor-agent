from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.models import Base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./eval.db")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # True yapınca SQL sorgularını loglar, debug için
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def init_db():
    """Tabloları oluştur — uygulama başlarken çağrılır."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Veritabanı hazır.")

async def get_db():
    """FastAPI dependency injection için."""
    async with AsyncSessionLocal() as session:
        yield session