# database/scripts/vectorize_tipo_incidencia.py

import asyncio
import asyncpg
import json
from pathlib import Path
from config.settings import get_settings
from openai import AzureOpenAI
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VectorizeIncidencia")

class TipoIncidenciaVectorizer:
    def __init__(self):
        self.settings = get_settings()
        db = self.settings.database
        self.conn_str = f"postgresql://{db.user}:{db.password}@{db.host}:{db.port}/{db.name}"
        self.embedding_deployment = os.getenv("LLM_AZURE_EMBEDDING_DEPLOYMENT")

        self.client = AzureOpenAI(
            api_key=os.getenv("LLM_AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("LLM_AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("LLM_AZURE_API_VERSION")
        )

    async def run(self):
        conn = await asyncpg.connect(self.conn_str)

        # Paso 1: Crear tabla base
        await conn.execute("""
        DROP TABLE IF EXISTS tipo_incidencia;
        CREATE TABLE tipo_incidencia (
            id SERIAL PRIMARY KEY,
            tipo_id TEXT UNIQUE,
            tipo_incidencia TEXT UNIQUE NOT NULL,
            descripcion TEXT
        );
        """)

        # Paso 2: Leer y cargar incidencias
        path = Path("data/eroski_incidents.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        incidentes = data.get("incident_types", {})
        for i, (tipo, contenido) in enumerate(incidentes.items(), start=1):
            tipo_id = f"ID{str(i).zfill(3)}"
            descripcion = contenido.get("description", "")
            await conn.execute("""
                INSERT INTO tipo_incidencia (tipo_id, tipo_incidencia, descripcion)
                VALUES ($1, $2, $3)
            """, tipo_id, tipo, descripcion)

        logger.info(f"✅ Insertados {len(incidentes)} tipos en tipo_incidencia")

        # Paso 3: Crear tabla vectorizada
        await conn.execute("""
        DROP TABLE IF EXISTS tipo_incidencia_vectorizado;
        CREATE TABLE tipo_incidencia_vectorizado (
            tipo_incidencia TEXT PRIMARY KEY,
            embedding VECTOR(1536) NOT NULL
        );
        """)

        # Paso 4: Vectorizar descripciones
        rows = await conn.fetch("SELECT tipo_incidencia, descripcion FROM tipo_incidencia")
        for row in rows:
            tipo = row["tipo_incidencia"]
            descripcion = row["descripcion"]
            vector = await self.embed(descripcion)

            if not vector:
                logger.warning(f"❌ No se pudo vectorizar {tipo}")
                continue

            vector_str = f"[{', '.join(map(str, vector))}]"
            await conn.execute("""
                INSERT INTO tipo_incidencia_vectorizado (tipo_incidencia, embedding)
                VALUES ($1, $2)
            """, tipo, vector_str)

        logger.info("✅ Vectorización completada")
        await conn.close()

    async def embed(self, text: str):
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
    asyncio.run(TipoIncidenciaVectorizer().run())
