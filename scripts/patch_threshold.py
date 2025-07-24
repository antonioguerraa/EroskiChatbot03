# =====================================================
# patch_threshold.py - Parche rápido para threshold
# =====================================================

import re
from pathlib import Path

def patch_rag_threshold():
    """Parche rápido para bajar el threshold del RAG"""
    
    files_to_patch = [
        "nodes/optimized_eroski_knowledge_base.py",
        "nodes/improved_eroski_knowledge_base.py"
    ]
    
    print("🔧 APLICANDO PARCHE DE THRESHOLD")
    print("=" * 40)
    
    for file_path in files_to_patch:
        file_path = Path(file_path)
        
        if not file_path.exists():
            print(f"⚠️ Archivo no encontrado: {file_path}")
            continue
        
        try:
            # Leer archivo
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Aplicar parches
            original_content = content
            
            # Parche 1: self.min_similarity_threshold = 0.55
            content = re.sub(
                r'self\.min_similarity_threshold\s*=\s*0\.55',
                'self.min_similarity_threshold = 0.40  # PARCHEADO',
                content
            )
            
            # Parche 2: similarity_threshold=0.55
            content = re.sub(
                r'similarity_threshold\s*=\s*0\.55',
                'similarity_threshold=0.40  # PARCHEADO',
                content
            )
            
            # Parche 3: threshold > 0.55
            content = re.sub(
                r'>\s*0\.55',
                '> 0.40  # PARCHEADO',
                content
            )
            
            # Verificar si hubo cambios
            if content != original_content:
                # Crear backup
                backup_path = file_path.with_suffix('.py.backup')
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                
                # Guardar archivo parcheado
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"✅ {file_path} parcheado")
                print(f"💾 Backup: {backup_path}")
            else:
                print(f"ℹ️ {file_path} sin cambios necesarios")
        
        except Exception as e:
            print(f"❌ Error parcheando {file_path}: {e}")
    
    print("\n🎉 PARCHE COMPLETADO")
    print("🚀 Ahora ejecuta: python test_advanced_rag.py")

if __name__ == "__main__":
    patch_rag_threshold()