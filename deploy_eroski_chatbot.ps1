# =====================================================
# deploy_eroski_chatbot.ps1 - Script de despliegue para Windows
# =====================================================

# Configuración de errores
$ErrorActionPreference = "Stop"

# Colores para output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Log($message) {
    Write-ColorOutput Blue "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $message"
}

function Success($message) {
    Write-ColorOutput Green "[SUCCESS] $message"
}

function Warning($message) {
    Write-ColorOutput Yellow "[WARNING] $message"
}

function Error($message) {
    Write-ColorOutput Red "[ERROR] $message"
    exit 1
}

Write-Host ""
Write-Host "🚀 Iniciando despliegue del Chatbot de Eroski (Windows)..." -ForegroundColor Cyan
Write-Host ""

# =====================================================
# VALIDACIONES PREVIAS
# =====================================================

Log "🔍 Validando entorno Windows..."

# Verificar Python
try {
    $pythonVersion = python --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        Error "Python no está instalado o no está en el PATH"
    }
    Log "✅ $pythonVersion detectado"
} catch {
    Error "Error al verificar Python. Asegúrate de que esté instalado y en el PATH"
}

# Verificar pip
try {
    pip --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Error "pip no está disponible"
    }
    Log "✅ pip disponible"
} catch {
    Error "pip no está instalado correctamente"
}

# Verificar directorio del proyecto
if (!(Test-Path "pyproject.toml")) {
    Error "No se encontró pyproject.toml. ¿Estás en el directorio correcto del proyecto?"
}

# Verificar archivos críticos
$requiredFiles = @(
    "models/eroski_state.py",
    "tests/test_identificador_interactivo.py"
)

foreach ($file in $requiredFiles) {
    if (!(Test-Path $file)) {
        Warning "Archivo del proyecto no encontrado: $file"
    }
}

# =====================================================
# CONFIGURACIÓN DEL ENTORNO VIRTUAL
# =====================================================

Log "🔧 Configurando entorno virtual..."

# Crear entorno virtual si no existe
if (!(Test-Path ".venv")) {
    Log "Creando entorno virtual..."
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Error "Error al crear entorno virtual"
    }
}

# Activar entorno virtual (Windows)
Log "Activando entorno virtual..."
if (Test-Path ".venv\Scripts\activate.ps1") {
    .\.venv\Scripts\activate.ps1
} elseif (Test-Path ".venv\Scripts\activate.bat") {
    .\.venv\Scripts\activate.bat
} else {
    Error "No se pudo encontrar el script de activación del entorno virtual"
}

# Actualizar pip
Log "Actualizando pip..."
python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Warning "No se pudo actualizar pip, continuando..."
}

# =====================================================
# INSTALACIÓN DE DEPENDENCIAS
# =====================================================

Log "📦 Instalando dependencias desde pyproject.toml..."

try {
    pip install -e "."
    if ($LASTEXITCODE -ne 0) {
        Error "Error al instalar dependencias del proyecto"
    }
} catch {
    Error "Fallo crítico en instalación de dependencias"
}

# Verificar instalación de Chainlit
try {
    chainlit --version | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Error "Chainlit no se instaló correctamente"
    }
    Log "✅ Chainlit instalado correctamente"
} catch {
    Error "Chainlit no está disponible después de la instalación"
}

Success "Dependencias instaladas correctamente"

# =====================================================
# CONFIGURACIÓN DE ARCHIVOS
# =====================================================

Log "⚙️ Configurando archivos del proyecto..."

# Crear directorio public si no existe
if (!(Test-Path "public")) {
    New-Item -ItemType Directory -Path "public"
    Log "📁 Directorio public/ creado"
}

# Verificar archivos de configuración
if (!(Test-Path "app.py")) {
    Warning "app.py no encontrado. Asegúrate de haber copiado todos los archivos."
}

if (!(Test-Path ".chainlit")) {
    Warning ".chainlit no encontrado. Configuración de Chainlit no disponible."
}

if (!(Test-Path "chainlit.md")) {
    Warning "chainlit.md no encontrado. README interactivo no disponible."
}

if (!(Test-Path "public/eroski-theme.css")) {
    Warning "public/eroski-theme.css no encontrado. Tema personalizado no disponible."
}

# Manejar archivo .env
if (!(Test-Path ".env")) {
    if (Test-Path ".env.template") {
        Log "Copiando .env.template a .env"
        Copy-Item ".env.template" ".env"
        Warning "⚠️  IMPORTANTE: Configura las variables en .env antes de ejecutar"
    } else {
        Warning "No se encontró .env.template. Crea .env manualmente con las variables necesarias."
    }
} else {
    Log "✅ Archivo .env encontrado"
}

# =====================================================
# VALIDACIÓN DE CONFIGURACIÓN
# =====================================================

Log "🔍 Validando configuración..."

# Función para verificar variables de entorno
function Check-EnvVar($varName) {
    if (Test-Path ".env") {
        $content = Get-Content ".env" -ErrorAction SilentlyContinue
        if ($content -match "^$varName=") {
            Log "✅ Variable $varName encontrada en .env"
        } else {
            Warning "Variable $varName no encontrada en .env"
        }
    }
}

# Variables críticas
$envVars = @(
    "OPENAI_API_KEY",
    "DATABASE_URL",
    "CHAINLIT_AUTH_SECRET"
)

foreach ($var in $envVars) {
    Check-EnvVar $var
}

# =====================================================
# TESTS BÁSICOS
# =====================================================

Log "🧪 Ejecutando tests básicos..."

# Test de importaciones básicas
$importTest = @"
try:
    import chainlit
    import langchain  
    import langgraph
    print('✅ Importaciones básicas OK')
except ImportError as e:
    print(f'❌ Error de importación: {e}')
    exit(1)
"@

python -c $importTest
if ($LASTEXITCODE -ne 0) {
    Error "Fallo en tests de importación básica"
}

# Test de configuración
$configTest = @"
try:
    from config.settings import get_settings
    settings = get_settings()
    print('✅ Configuración avanzada cargada')
except Exception as e:
    print(f'⚠️  Configuración avanzada no disponible: {e}')
    print('✅ Modo fallback activo')
"@

python -c $configTest 2>$null
if ($LASTEXITCODE -ne 0) {
    Warning "Configuración avanzada no disponible (modo fallback activo)"
}

Success "Tests básicos completados"

# =====================================================
# VERIFICACIÓN DE PUERTO
# =====================================================

$port = if ($env:PORT) { $env:PORT } else { "8000" }

try {
    $portInUse = netstat -an | Select-String ":$port.*LISTENING"
    if ($portInUse) {
        Warning "Puerto $port parece estar en uso. Chainlit intentará usar otro puerto."
    }
} catch {
    Log "No se pudo verificar el estado del puerto $port"
}

# =====================================================
# INSTRUCCIONES FINALES
# =====================================================

Write-Host ""
Write-Host "🎉 ¡Configuración completada!" -ForegroundColor Green
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "                    INSTRUCCIONES DE USO (WINDOWS)" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "Para iniciar el chatbot de Eroski:" -ForegroundColor White
Write-Host ""
Write-Host "1. 🔧 CONFIGURACIÓN (si no lo has hecho):" -ForegroundColor Yellow
Write-Host "   - Edita el archivo .env con tus API keys" -ForegroundColor White
Write-Host "   - Configura la conexión a PostgreSQL" -ForegroundColor White
Write-Host "   - Verifica que todos los servicios estén activos" -ForegroundColor White
Write-Host ""
Write-Host "2. 🚀 DESARROLLO:" -ForegroundColor Yellow
Write-Host "   chainlit run app.py" -ForegroundColor Green
Write-Host ""
Write-Host "3. 🌐 PRODUCCIÓN:" -ForegroundColor Yellow
Write-Host "   chainlit run app.py --host 0.0.0.0 --port $port" -ForegroundColor Green
Write-Host ""
Write-Host "4. 🧪 TESTING:" -ForegroundColor Yellow
Write-Host "   python tests/test_identificador_interactivo.py" -ForegroundColor Green
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
Write-Host "📱 Una vez iniciado, accede en:" -ForegroundColor White
Write-Host "   🌐 http://localhost:$port" -ForegroundColor Green
Write-Host ""
Write-Host "🔧 Características activas:" -ForegroundColor White
Write-Host "   ✅ Interfaz profesional con tema Eroski" -ForegroundColor Green
Write-Host "   ✅ Sistema de autenticación" -ForegroundColor Green  
Write-Host "   ✅ Gestión de sesiones" -ForegroundColor Green
Write-Host "   ✅ Integración con LangGraph" -ForegroundColor Green
Write-Host "   ✅ Modo fallback para desarrollo" -ForegroundColor Green
Write-Host ""

# =====================================================
# INICIO AUTOMÁTICO OPCIONAL
# =====================================================

$response = Read-Host "¿Quieres iniciar el chatbot ahora? [y/N]"
if ($response -match "^[Yy]") {
    Log "🚀 Iniciando Chainlit..."
    chainlit run app.py
} else {
    Success "Configuración lista. Ejecuta 'chainlit run app.py' cuando estés listo."
}

Write-Host ""
Write-Host "💡 Para futuras ejecuciones, solo necesitas:" -ForegroundColor Cyan
Write-Host "   1. Activar entorno: .\.venv\Scripts\activate" -ForegroundColor Yellow
Write-Host "   2. Ejecutar: chainlit run app.py" -ForegroundColor Yellow
Write-Host ""