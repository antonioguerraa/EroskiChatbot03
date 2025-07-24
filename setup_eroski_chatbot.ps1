# =====================================================
# setup_eroski_chatbot.ps1 - Script de configuración para Windows PowerShell
# =====================================================

Write-Host "🛒 Configurando Chatbot de Incidencias Eroski" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green

# Verificar Python
try {
    $pythonVersion = python --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Python encontrado: $pythonVersion" -ForegroundColor Green
    } else {
        throw "Python no encontrado"
    }
} catch {
    Write-Host "❌ Python no está instalado o no está en el PATH" -ForegroundColor Red
    Write-Host "   Descarga Python desde: https://www.python.org/downloads/" -ForegroundColor Yellow
    exit 1
}

# Crear entorno virtual si no existe
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creando entorno virtual..." -ForegroundColor Blue
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Error creando entorno virtual" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "✅ Entorno virtual ya existe" -ForegroundColor Green
}

# Activar entorno virtual
Write-Host "🔄 Activando entorno virtual..." -ForegroundColor Blue
& ".venv\Scripts\Activate.ps1"

# Verificar que el entorno virtual está activo
if ($env:VIRTUAL_ENV) {
    Write-Host "✅ Entorno virtual activado: $env:VIRTUAL_ENV" -ForegroundColor Green
} else {
    Write-Host "⚠️  Entorno virtual no se activó correctamente" -ForegroundColor Yellow
}

# Actualizar pip
Write-Host "📥 Actualizando pip..." -ForegroundColor Blue
python -m pip install --upgrade pip

# Instalar dependencias principales
Write-Host "📥 Instalando dependencias..." -ForegroundColor Blue

$dependencies = @(
    "chainlit",
    "langgraph", 
    "langchain",
    "langchain-openai",
    "python-dotenv"
)

foreach ($dep in $dependencies) {
    Write-Host "   Instalando $dep..." -ForegroundColor Cyan
    pip install $dep
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Error instalando $dep" -ForegroundColor Red
        exit 1
    }
}

Write-Host "✅ Dependencias instaladas correctamente" -ForegroundColor Green

# Crear archivo .env si no existe
if (-not (Test-Path ".env")) {
    Write-Host "📝 Creando archivo .env..." -ForegroundColor Blue
    
    $envContent = @"
# Configuración del Chatbot Eroski

# OpenAI API Key (requerido)
OPENAI_API_KEY=tu_api_key_aqui

# Configuración de la aplicación
APP_NAME=Eroski Chatbot
APP_DEBUG_MODE=false

# Configuración de Chainlit
CHAINLIT_DEBUG=false
CHAINLIT_HOST=localhost
CHAINLIT_PORT=8000

# Configuración de logging
LOG_LEVEL=INFO
"@
    
    $envContent | Out-File -FilePath ".env" -Encoding UTF8
    Write-Host "✅ Archivo .env creado" -ForegroundColor Green
} else {
    Write-Host "✅ Archivo .env ya existe" -ForegroundColor Green
}

# Crear estructura de directorios si no existe
Write-Host "📁 Verificando estructura de directorios..." -ForegroundColor Blue
$directories = @("logs", "data", "config")

foreach ($dir in $directories) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
        Write-Host "   📁 Directorio $dir creado" -ForegroundColor Cyan
    }
}

# Crear archivo .chainlit/config.toml si no existe
if (-not (Test-Path ".chainlit")) {
    New-Item -ItemType Directory -Path ".chainlit" | Out-Null
}

if (-not (Test-Path ".chainlit/config.toml")) {
    Write-Host "📝 Creando configuración de Chainlit..." -ForegroundColor Blue
    
    $chainlitConfig = @"
[project]
# Configuración del proyecto Chainlit para Eroski
name = "Asistente de Incidencias Eroski"

[UI]
name = "🛒 Eroski - Asistente de Incidencias"
show_readme_as_default = false
default_theme = "light"

[features]
prompt_playground = false
multi_modal = false
speech_to_text = false

[meta]
generated_by = "0.8.0"
"@
    
    $chainlitConfig | Out-File -FilePath ".chainlit/config.toml" -Encoding UTF8
}

Write-Host ""
Write-Host "🎉 ¡Configuración completada!" -ForegroundColor Green
Write-Host ""
Write-Host "📋 Próximos pasos:" -ForegroundColor Yellow
Write-Host "1. Edita el archivo .env y añade tu OPENAI_API_KEY" -ForegroundColor White
Write-Host "2. Activa el entorno virtual: .venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "3. Ejecuta el chatbot: chainlit run chainlit_app.py -w" -ForegroundColor White
Write-Host ""
Write-Host "🔧 Comandos útiles:" -ForegroundColor Yellow
Write-Host "   - Activar entorno: .venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "   - Desactivar entorno: deactivate" -ForegroundColor White
Write-Host "   - Ejecutar chatbot: chainlit run chainlit_app.py -w" -ForegroundColor White
Write-Host "   - Ver dependencias: pip list" -ForegroundColor White
Write-Host ""
Write-Host "⚠️  IMPORTANTE: No olvides configurar tu OPENAI_API_KEY en el archivo .env" -ForegroundColor Red