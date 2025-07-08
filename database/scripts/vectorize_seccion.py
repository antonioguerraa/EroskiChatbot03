# scripts/vectorize_secciones.py

import asyncio
import asyncpg
import logging
from config.settings import get_settings
from utils.llm.providers import get_vectorizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VectorizeSecciones")

class SeccionVectorizer:
    def __init__(self):
        self.settings = get_settings()
        self.db_config = self.settings.database
        self.connection_string = (
            f"postgresql://{self.db_config.user}:{self.db_config.password}"
            f"@{self.db_config.host}:{self.db_config.port}/{self.db_config.name}"
        )

    async def run(self):
        logger.info("📦 Iniciando vectorización de secciones")
        conn = await asyncpg.connect(self.connection_string)

        # Añadir restricción UNIQUE si no existe

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS departamentos_vectorizados (
                id SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL,
                embedding vector(1536),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        try:
            await conn.execute("""
                ALTER TABLE departamentos_vectorizados
                ADD CONSTRAINT unique_nombre UNIQUE(nombre);
            """)
        except Exception as e:
            logger.info(f"ℹ️ Restricción UNIQUE ya existe o no se pudo aplicar: {e}")

        # Leer nombres únicos
        rows = await conn.fetch("SELECT DISTINCT nombre FROM departamento WHERE nombre IS NOT NULL")

        for i, row in enumerate(rows, 1):
            nombre = row["nombre"].strip()
            logger.info(f"🔹 Vectorizando ({i}/{len(rows)}): {nombre}")

            vector = await asyncio.to_thread(get_vectorizer().embed, nombre)
            if not vector:
                logger.warning(f"⚠️ No se generó embedding para: {nombre}")
                continue

            vector_str = f"[{', '.join(map(str, vector))}]"
            await conn.execute("""
                INSERT INTO departamentos_vectorizados (nombre, embedding)
                VALUES ($1, $2)
                ON CONFLICT (nombre) DO NOTHING
            """, nombre, vector_str)

        await conn.close()
        logger.info("✅ Vectorización finalizada")


if __name__ == "__main__":
    asyncio.run(SeccionVectorizer().run())
