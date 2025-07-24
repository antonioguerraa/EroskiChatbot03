@echo off
REM =====================================================
REM setup_eroski_chatbot.bat - Script de configuración para Windows CMD
REM =====================================================

echo 🛒 Configurando Chatbot de Incidencias Eroski
echo ==============================================

REM Verificar Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ❌ Python no está instalado o no está en el PATH
    echo    Descarga Python desde: https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo ✅ Python encontrado: %PYTHON_VERSION%

REM Crear entorno virtual si no existe
if not exist ".venv" (
    echo 📦 Creando entorno virtual...
    python -m venv .venv
    if %ERRORLEVEL% NEQ 0 (
        echo ❌ Error creando entorno virtual
        pause
        exit /b 1
    )
) else (
    echo ✅ Entorno virtual ya existe
)

REM Activar entorno virtual
echo 🔄 Activando entorno virtual...
call .venv\Scripts\activate.bat

REM Actualizar pip
echo 📥 Actualizando pip...
python -m pip install --upgrade pip

REM Instalar dependencias
echo 📥 Instalando dependencias...
pip install chainlit
pip install langgraph
pip install langchain
pip install langchain-openai
pip install python-dotenv

if %ERRORLEVEL% NEQ 0 (
    echo ❌ Error instalando dependencias
    pause
    exit /b 1
)

echo ✅ Dependencias instaladas correctamente

REM Crear archivo .env si no existe
if not exist ".env" (
    echo 📝 Creando archivo .env...
    (
        echo # Configuración del Chatbot Eroski
        echo.
        echo # OpenAI API Key ^(requerido^)
        echo OPENAI_API_KEY=tu_api_key_aqui
        echo.
        echo # Configuración de la aplicación
        echo APP_NAME=Eroski Chatbot
        echo APP_DEBUG_MODE=false
        echo.
        echo # Configuración de Chainlit
        echo CHAINLIT_DEBUG=false
        echo CHAINLIT_HOST=localhost
        echo CHAINLIT_PORT=8000
        echo.
        echo # Configuración de logging
        echo LOG_LEVEL=INFO
    ) > .env
    echo ✅ Archivo .env creado
) else (
    echo ✅ Archivo .env ya existe
)

REM Crear estructura de directorios
echo 📁 Verificando estructura de directorios...
if not exist "logs" mkdir logs
if not exist "data" mkdir data
if not exist "config" mkdir config

REM Crear configuración de Chainlit
if not exist ".chainlit" mkdir .chainlit
if not exist ".chainlit\config.toml" (
    echo 📝 Creando configuración de Chainlit...
    (
        echo [project]
        echo # Configuración del proyecto Chainlit para Eroski
        echo name = "Asistente de Incidencias Eroski"
        echo.
        echo [UI]
        echo name = "🛒 Eroski - Asistente de Incidencias"
        echo show_readme_as_default = false
        echo default_theme = "light"
        echo.
        echo [features]
        echo prompt_playground = false
        echo multi_modal = false
        echo speech_to_text = false
        echo.
        echo [meta]
        echo generated_by = "0.8.0"
    ) > .chainlit\config.toml
)

echo.
echo 🎉 ¡Configuración completada!
echo.
echo 📋 Próximos pasos:
echo 1. Edita el archivo .env y añade tu OPENAI_API_KEY
echo 2. Activa el entorno virtual: .venv\Scripts\activate.bat
echo 3. Ejecuta el chatbot: chainlit run chainlit_app.py -w
echo.
echo 🔧 Comandos útiles:
echo    - Activar entorno: .venv\Scripts\activate.bat
echo    - Desactivar entorno: deactivate
echo    - Ejecutar chatbot: chainlit run chainlit_app.py -w
echo    - Ver dependencias: pip list
echo.
echo ⚠️  IMPORTANTE: No olvides configurar tu OPENAI_API_KEY en el archivo .env
echo.
pause