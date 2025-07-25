#!/usr/bin/env python3
"""
Script de Limpieza - Chatbot Eroski
Elimina archivos duplicados y no utilizados detectados en el análisis
"""

import os
import shutil
from pathlib import Path
from typing import List

class EroskiProjectCleaner:
    """Limpiador de archivos no utilizados del proyecto Eroski"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.removed_files = []
        self.removed_dirs = []
        self.errors = []
        
    def remove_file_safe(self, file_path: str) -> bool:
        """Eliminar archivo de forma segura"""
        try:
            full_path = self.project_root / file_path
            if full_path.exists():
                full_path.unlink()
                self.removed_files.append(file_path)
                print(f"✅ Eliminado: {file_path}")
                return True
            else:
                print(f"⚠️ No existe: {file_path}")
                return False
        except Exception as e:
            self.errors.append(f"❌ Error eliminando {file_path}: {e}")
            print(f"❌ Error eliminando {file_path}: {e}")
            return False
    
    def remove_directory_safe(self, dir_path: str) -> bool:
        """Eliminar directorio de forma segura"""
        try:
            full_path = self.project_root / dir_path
            if full_path.exists() and full_path.is_dir():
                shutil.rmtree(full_path)
                self.removed_dirs.append(dir_path)
                print(f"✅ Directorio eliminado: {dir_path}")
                return True
            else:
                print(f"⚠️ Directorio no existe: {dir_path}")
                return False
        except Exception as e:
            self.errors.append(f"❌ Error eliminando directorio {dir_path}: {e}")
            print(f"❌ Error eliminando directorio {dir_path}: {e}")
            return False
    
    def clean_redundant_setup_scripts(self):
        """Eliminar scripts de configuración redundantes"""
        print("\n🧹 Limpiando scripts de configuración redundantes...")
        
        redundant_scripts = [
            "setup_eroski_chatbot.ps1",
            "setup_eroski_chatbot.bat", 
            "deploy_eroski_chatbot.ps1",
            "requirements.txt"  # Usar solo pyproject.toml
        ]
        
        for script in redundant_scripts:
            self.remove_file_safe(script)
    
    def clean_duplicate_tests(self):
        """Limpiar tests duplicados o específicos"""
        print("\n🧹 Limpiando tests duplicados...")
        
        # Tests que pueden ser consolidados
        potential_duplicate_tests = [
            "tests/test_identificacion_flujo.py",  # Consolidar con test_grafo.py
            "tests/test_identificacion_flujo_is_async.py",  # Duplicado
            "tests/test_interactive_identification.py",  # Funcionalidad similar
            "tests/testv02.py",  # Versión obsoleta
            "tests/test.py"  # Nombre genérico, probablemente obsoleto
        ]
        
        for test_file in potential_duplicate_tests:
            if self.file_confirmation(f"¿Eliminar {test_file}? (es duplicado/obsoleto)"):
                self.remove_file_safe(test_file)
    
    def clean_main_files(self):
        """Limpiar archivos principales duplicados"""
        print("\n🧹 Consolidando archivos principales...")
        
        # Estos archivos serán reemplazados por el workflow refactorizado
        main_files_to_clean = [
            "chainlit_app.py",  # Será reemplazado por el workflow refactorizado
            "main.py"  # Múltiples entry points, mantener solo uno
        ]
        
        for main_file in main_files_to_clean:
            if self.file_confirmation(f"¿Mover {main_file} a backup? (será reemplazado)"):
                self.backup_and_remove(main_file)
    
    def backup_and_remove(self, file_path: str):
        """Crear backup antes de eliminar"""
        try:
            full_path = self.project_root / file_path
            if full_path.exists():
                backup_path = self.project_root / "backup" / file_path
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(full_path, backup_path)
                full_path.unlink()
                print(f"✅ {file_path} movido a backup/")
        except Exception as e:
            print(f"❌ Error creando backup de {file_path}: {e}")
    
    def clean_unused_interfaces(self):
        """Limpiar interfaces no utilizadas"""
        print("\n🧹 Limpiando interfaces no utilizadas...")
        
        # Directorios de interfaces que pueden no estar en uso
        interface_dirs = [
            "interfaces",  # Si no se está usando
        ]
        
        for interface_dir in interface_dirs:
            if (self.project_root / interface_dir).exists():
                if self.file_confirmation(f"¿Eliminar directorio {interface_dir}? (puede estar no usado)"):
                    self.remove_directory_safe(interface_dir)
    
    def file_confirmation(self, message: str) -> bool:
        """Pedir confirmación del usuario"""
        response = input(f"{message} [y/N]: ").strip().lower()
        return response in ['y', 'yes', 'sí', 's']
    
    def create_structure_for_refactor(self):
        """Crear estructura de directorios para la refactorización"""
        print("\n📁 Creando estructura para refactorización...")
        
        new_dirs = [
            "src",
            "src/core",
            "src/nodes", 
            "src/utils",
            "src/models",
            "backup",
            "docs"
        ]
        
        for new_dir in new_dirs:
            dir_path = self.project_root / new_dir
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"📁 Directorio creado/verificado: {new_dir}")
    
    def show_summary(self):
        """Mostrar resumen de la limpieza"""
        print("\n" + "="*50)
        print("📊 RESUMEN DE LIMPIEZA")
        print("="*50)
        
        print(f"✅ Archivos eliminados: {len(self.removed_files)}")
        for file in self.removed_files:
            print(f"   - {file}")
        
        print(f"\n✅ Directorios eliminados: {len(self.removed_dirs)}")
        for dir in self.removed_dirs:
            print(f"   - {dir}")
        
        if self.errors:
            print(f"\n❌ Errores encontrados: {len(self.errors)}")
            for error in self.errors:
                print(f"   - {error}")
        
        print(f"\n🎯 SIGUIENTE PASO:")
        print("1. Crear el archivo 'eroski_app.py' con el workflow refactorizado")
        print("2. Mover archivos existentes a la nueva estructura src/")
        print("3. Actualizar imports en el código restante")
        print("4. Ejecutar tests para verificar funcionamiento")
    
    def run_full_cleanup(self):
        """Ejecutar limpieza completa"""
        print("🧹 INICIANDO LIMPIEZA DEL PROYECTO EROSKI")
        print("="*50)
        
        # Confirmación general
        if not self.file_confirmation("¿Proceder con la limpieza? (se harán backups)"):
            print("❌ Limpieza cancelada por el usuario")
            return
        
        # Ejecutar limpieza por pasos
        self.clean_redundant_setup_scripts()
        self.clean_duplicate_tests()
        self.clean_main_files()
        self.clean_unused_interfaces()
        self.create_structure_for_refactor()
        
        # Mostrar resumen
        self.show_summary()

def main():
    """Función principal"""
    print("🛒 EROSKI PROJECT CLEANER")
    print("Herramienta para limpiar archivos duplicados y no utilizados")
    print()
    
    # Verificar que estamos en el directorio correcto
    if not Path("pyproject.toml").exists():
        print("❌ No se encuentra pyproject.toml")
        print("   ¿Estás ejecutando desde el directorio raíz del proyecto?")
        return
    
    # Crear cleaner y ejecutar
    cleaner = EroskiProjectCleaner()
    
    # Mostrar opciones
    print("Opciones disponibles:")
    print("1. Limpieza completa (recomendado)")
    print("2. Solo scripts de configuración")
    print("3. Solo tests duplicados")
    print("4. Solo crear estructura para refactor")
    print("5. Cancelar")
    
    choice = input("\nSelecciona una opción [1-5]: ").strip()
    
    if choice == "1":
        cleaner.run_full_cleanup()
    elif choice == "2":
        cleaner.clean_redundant_setup_scripts()
        cleaner.show_summary()
    elif choice == "3":
        cleaner.clean_duplicate_tests()
        cleaner.show_summary()
    elif choice == "4":
        cleaner.create_structure_for_refactor()
    elif choice == "5":
        print("❌ Operación cancelada")
    else:
        print("❌ Opción no válida")

if __name__ == "__main__":
    main()