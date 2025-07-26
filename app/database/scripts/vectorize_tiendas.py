# scripts/vectorize_tiendas.py

import asyncio
import asyncpg
import os
from openai import AzureOpenAI
from config.settings import get_settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VectorizeTiendas")

class TiendaVectorizer:
    def __init__(self):
        self.settings = get_settings()
        self.db_config = self.settings.database
        self.connection_string = (
            f"postgresql://{self.db_config.user}:{self.db_config.password}"
            f"@{self.db_config.host}:{self.db_config.port}/{self.db_config.name}"
        )
        self.embedding_deployment = os.getenv("LLM_AZURE_EMBEDDING_DEPLOYMENT")
        self.client = AzureOpenAI(
            api_key=os.getenv("LLM_AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("LLM_AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("LLM_AZURE_API_VERSION")
        )

    async def run(self):
        logger.info("📦 Iniciando vectorización de tiendas")
        conn = await asyncpg.connect(self.connection_string)

        # Crear tabla si no existe
        await conn.execute("""
            ALTER TABLE tiendas_vectorizadas
            ADD CONSTRAINT unique_nombre_tienda UNIQUE(nombre_tienda);
        """)

        # Leer nombres únicos
        rows = await conn.fetch("SELECT DISTINCT nombre_tienda FROM maestro_tiendas WHERE nombre_tienda IS NOT NULL")

        for i, row in enumerate(rows, 1):
            nombre = row["nombre_tienda"].strip()

            logger.info(f"🔹 Vectorizando ({i}/{len(rows)}): {nombre}")
            vector = await self.generate_embedding(nombre)
            if not vector:
                logger.warning(f"⚠️ No se generó embedding para: {nombre}")
                continue

            if vector:
                vector_str = f"[{', '.join(map(str, vector))}]"
                await conn.execute("""
                    INSERT INTO tiendas_vectorizadas (nombre_tienda, embedding)
                    VALUES ($1, $2)
                    ON CONFLICT (nombre_tienda) DO NOTHING
                """, nombre, vector_str)

        await conn.close()
        logger.info("✅ Vectorización finalizada")

    async def generate_embedding(self, text: str):
        try:
            response = self.client.embeddings.create(
                model=self.embedding_deployment,
                input=text,
                encoding_format="float"
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"❌ Error generando embedding: {e}")
            return None


if __name__ == "__main__":
    asyncio.run(TiendaVectorizer().run())
