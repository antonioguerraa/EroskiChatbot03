# =====================================================
# setup_eroski_uv.ps1 - Script simplificado para Windows + UV
# =====================================================

Write-Host ""
Write-Host "🚀 Configurando Chatbot de Eroski con UV..." -ForegroundColor Cyan
Write-Host ""

# Verificar UV
try {
    $uvVersion = uv --version
    Write-Host "✅ UV detectado: $uvVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ ERROR: UV no está instalado" -ForegroundColor Red
    Write-Host "Instala UV desde: https://github.com/astral-sh/uv" -ForegroundColor Yellow
    exit 1
}

# Verificar pyproject.toml
if (!(Test-Path "pyproject.toml")) {
    Write-Host "❌ ERROR: No se encontró pyproject.toml" -ForegroundColor Red
    Write-Host "¿Estás en el directorio correcto del proyecto?" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Proyecto Eroski detectado" -ForegroundColor Green

# Crear directorio public
if (!(Test-Path "public")) {
    New-Item -ItemType Directory -Path "public" | Out-Null
    Write-Host "📁 Directorio public/ creado" -ForegroundColor Blue
}

# Sincronizar dependencias con UV
Write-Host ""
Write-Host "📦 Sincronizando dependencias con UV..." -ForegroundColor Blue

try {
    uv sync
    Write-Host "✅ Dependencias sincronizadas" -ForegroundColor Green
} catch {
    Write-Host "⚠️ Problema con uv sync, instalando manualmente..." -ForegroundColor Yellow
    uv add chainlit
    uv add langchain
    uv add langgraph
    uv add langchain-openai
    uv add python-dotenv
}

# Verificar Chainlit
Write-Host ""
Write-Host "🔍 Verificando Chainlit..." -ForegroundColor Blue

try {
    uv run chainlit --version | Out-Null
    Write-Host "✅ Chainlit disponible" -ForegroundColor Green
} catch {
    Write-Host "❌ ERROR: Chainlit no funciona" -ForegroundColor Red
    exit 1
}

# Verificar archivos críticos
Write-Host ""
Write-Host "📁 Verificando archivos..." -ForegroundColor Blue

$files = @{
    "app.py" = "Interfaz Chainlit"
    ".chainlit" = "Configuración"
    "chainlit.md" = "README"
    "public/eroski-theme.css" = "Tema CSS"
}

foreach ($file in $files.Keys) {
    if (Test-Path $file) {
        Write-Host "✅ $file" -ForegroundColor Green
    } else {
        Write-Host "❌ $file - $($files[$file])" -ForegroundColor Red
    }
}

# Manejar .env
if (!(Test-Path ".env")) {
    if (Test-Path ".env.template") {
        Copy-Item ".env.template" ".env"
        Write-Host "📋 .env creado desde template" -ForegroundColor Blue
    } else {
        Write-Host "⚠️ Necesitas crear archivo .env" -ForegroundColor Yellow
    }
}

# Test básico
Write-Host ""
Write-Host "🧪 Test básico..." -ForegroundColor Blue

$testScript = @"
try:
    import chainlit
    print('✅ Chainlit OK')
except:
    print('❌ Chainlit falla')
    exit(1)
"@

uv run python -c $testScript

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Test básico pasado" -ForegroundColor Green
} else {
    Write-Host "❌ Test básico fallido" -ForegroundColor Red
    exit 1
}

# Información final
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "                    CONFIGURACIÓN COMPLETADA" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "🚀 COMANDOS PRINCIPALES:" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Iniciar chatbot:" -ForegroundColor White
Write-Host "  uv run chainlit run app.py" -ForegroundColor Green
Write-Host ""
Write-Host "  Producción:" -ForegroundColor White
Write-Host "  uv run chainlit run app.py --host 0.0.0.0 --port 8000" -ForegroundColor Green
Write-Host ""
Write-Host "  Tests:" -ForegroundColor White
Write-Host "  uv run python tests/test_identificador_interactivo.py" -ForegroundColor Green
Write-Host ""
Write-Host "📱 Acceso: http://localhost:8000" -ForegroundColor Blue
Write-Host ""

# Preguntar si iniciar
$response = Read-Host "¿Iniciar chatbot ahora? [y/N]"
if ($response -eq "y" -or $response -eq "Y") {
    Write-Host ""
    Write-Host "🚀 Iniciando Chainlit..." -ForegroundColor Green
    uv run chainlit run app.py
} else {
    Write-Host ""
    Write-Host "✅ Listo! Ejecuta: uv run chainlit run app.py" -ForegroundColor Green
}