import asyncio
from nodes.identificacion_manual import IdentificacionManualNode  # Ajusta la ruta según tu estructura

async def test():
    servicio = IdentificacionManualNode()

    nombre = "Durangg"  # Entrada con typo
    resultado = await servicio._buscar_tienda_mas_parecida(nombre)

    if resultado:
        print(f"✅ Tienda más parecida a '{nombre}': {resultado['nombre']} (distancia: {resultado['distancia']:.4f})")
    else:
        print(f"❌ No se encontró ninguna tienda parecida a '{nombre}'")

if __name__ == "__main__":
    asyncio.run(test())
