# Creamos un archivo limpio para integrar en el proyecto como "utils/limpieza_chunks.py"

import re

def clean_chunk_text(text: str) -> str:
    """
    Limpia el texto de un chunk eliminando ruido:
    - Líneas numéricas o de etiquetas repetidas
    - Valores como "0.000", "0.00"
    - Caracteres no imprimibles
    - Duplicados
    - Compacta espacios en blanco

    También refuerza encabezados como "2.3.24." para destacarlos.
    """
    lines = text.split("\\n")
    clean_lines = []
    seen_lines = set()

    for line in lines:
        line = line.strip()

        # Ignorar líneas vacías o duplicadas
        if not line or line in seen_lines:
            continue

        # Ignorar líneas que solo contienen números, ceros o patrones ruidosos
        if re.match(r"^0+(\\.0+)?$", line):  # solo ceros
            continue
        if re.match(r"^\\d+(\\.\\d+)?$", line):  # solo número
            continue
        if re.match(r"^[A-Z\\s]*\\d{1,2}\\s*-\\s*[A-Z\\s]+$", line):  # ej: "03 - PATATAS"
            continue
# Resaltar secciones tipo 6.2. NOMBRE
        if re.match(r"^\d+(\.\d+)*\.\s+[A-ZÁÉÍÓÚÑ ]+", line):
            line = f"\n🔹 {line.strip()}\n"
            
        # Detectar encabezados tipo "2.3.24." y resaltarlos
        if re.match(r"^\\d{1,2}\\.\\d{1,2}(\\.\\d{1,2})?", line):
            line = f"\\n🔹 {line}\\n"

        seen_lines.add(line)
        clean_lines.append(line)

    return "\\n".join(clean_lines)
