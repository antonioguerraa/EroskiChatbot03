# 🛒 Chatbot de Incidencias Eroski - Integración Chainlit

## 🎯 Descripción

Chatbot conversacional para el manejo de incidencias técnicas en tiendas Eroski, construido con **LangGraph** y **Chainlit**. Esta aplicación permite a los empleados reportar y resolver incidencias de manera intuitiva a través de una interfaz web moderna.

## ✨ Características

- 🤖 **Conversación Natural**: Interfaz intuitiva basada en chat
- 🔄 **Flujo Inteligente**: Orquestación automática con LangGraph  
- 🔐 **Identificación Automática**: Reconocimiento de empleados por email/ID
- 🎯 **Clasificación Inteligente**: Categorización automática de incidencias
- 📋 **Soluciones Contextuales**: Respuestas basadas en base de conocimiento
- 🚀 **Escalación Automática**: Derivación a supervisores cuando es necesario

## 🏗️ Arquitectura

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Chainlit UI   │ -> │   LangGraph     │ -> │   Nodos de      │
│   (Frontend)    │    │   (Orquestador) │    │   Procesamiento │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │                       │
        v                       v                       v
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Estado de      │    │  Flujo de       │    │  Base de        │
│  Conversación   │    │  Conversación   │    │  Conocimiento   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Instalación Rápida

### 1. Configuración Automática
```bash
# Descargar y ejecutar script de setup
chmod +x setup_eroski_chatbot.sh
./setup_eroski_chatbot.sh
```

### 2. Configuración Manual
```bash
# 1. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias
pip install chainlit langgraph langchain langchain-openai python-dotenv

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu OPENAI_API_KEY
```

### 3. Configurar API Key
```bash
# Editar archivo .env
nano .env

# Añadir tu clave de OpenAI
OPENAI_API_KEY=sk-tu-clave-aqui
```

## 🎮 Uso

### Ejecutar el Chatbot
```bash
# Activar entorno virtual
source .venv/bin/activate

# Ejecutar aplicación
chainlit run chainlit_app.py -w
```

La aplicación estará disponible en: http://localhost:8000

### Flujo de Conversación Típico

1. **👋 Saludo Inicial**
   ```
   Usuario: Hola, tengo un problema con la impresora
   Bot: ¡Hola! Para ayudarte, necesito identificarte. 
        ¿Podrías proporcionarme tu email corporativo?
   ```

2. **🔐 Identificación**
   ```
   Usuario: juan.perez@eroski.es
   Bot: ¡Perfecto Juan! Ya te tengo identificado. 
        Ahora cuéntame más sobre el problema con la impresora.
   ```

3. **🎯 Clasificación de Incidencia**
   ```
   Usuario: La impresora no imprime las etiquetas de precio
   Bot: Entiendo. Es un problema de impresión de etiquetas. 
        ¿Has verificado si tiene papel y tinta?
   ```

4. **💡 Solución o Escalación**
   ```
   Bot: He encontrado la solución. Intenta estos pasos:
        1. Verificar conexión USB
        2. Reiniciar impresora
        3. Verificar driver actualizado
        
        ¿Te ha funcionado?
   ```

## 🔧 Configuración Avanzada

### Variables de Entorno
```bash
# Aplicación
APP_NAME=Eroski Chatbot
APP_DEBUG_MODE=false

# OpenAI
OPENAI_API_KEY=tu_api_key

# Chainlit
CHAINLIT_DEBUG=false
CHAINLIT_HOST=localhost
CHAINLIT_PORT=8000

# Logging
LOG_LEVEL=INFO
```

### Personalización del UI
Edita `.chainlit/config.toml` para personalizar:
- Nombre de la aplicación
- Tema visual
- Funcionalidades habilitadas

### Modo Debug
Para habilitar información de debug:
```bash
export CHAINLIT_DEBUG=true
chainlit run chainlit_app.py -w
```

## 📊 Monitoreo y Logs

### Ver Logs en Tiempo Real
```bash
# Logs de la aplicación
tail -f logs/eroski_chatbot.log

# Logs de Chainlit
tail -f ~/.chainlit/logs/chainlit.log
```

### Métricas de Conversación
El sistema registra automáticamente:
- Número de sesiones
- Tiempo de resolución
- Tipos de incidencias más comunes
- Escalaciones a supervisor

## 🧪 Testing

### Probar Componentes Individuales
```bash
# Probar solo el grafo LangGraph
python tests/test_identificador_grafo_interactivo.py

# Probar nodos específicos
python tests/test_nodes/
```

### Probar Integración Completa
```bash
# Ejecutar en modo test
export CHAINLIT_DEBUG=true
chainlit run chainlit_app.py
```

## 🚨 Solución de Problemas

### Error: "OpenAI API Key no configurada"
```bash
# Verificar que la variable esté configurada
echo $OPENAI_API_KEY

# Si está vacía, configurar en .env
echo "OPENAI_API_KEY=tu_clave" >> .env
```

### Error: "No se puede importar módulo"
```bash
# Verificar que estés en el entorno virtual
which python
# Debe mostrar: /path/to/project/.venv/bin/python

# Si no, activar entorno
source .venv/bin/activate
```

### Error: "Puerto ya en uso"
```bash
# Cambiar puerto en .env
CHAINLIT_PORT=8001

# O matar proceso existente
lsof -ti:8000 | xargs kill
```

## 📈 Próximas Mejoras

- [ ] Integración con base de datos de incidencias
- [ ] Métricas en tiempo real con dashboard
- [ ] Soporte multiidioma
- [ ] Integración con sistema de tickets
- [ ] Notificaciones push para supervisores
- [ ] Export de conversaciones a PDF

## 🤝 Contribuir

1. Fork del repositorio
2. Crear rama feature (`git checkout -b feature/nueva-funcionalidad`)
3. Commit cambios (`git commit -am 'Añadir nueva funcionalidad'`)
4. Push a la rama (`git push origin feature/nueva-funcionalidad`)
5. Crear Pull Request

## 📞 Soporte

Para soporte técnico o preguntas:
- 📧 Email: soporte.chatbot@eroski.es
- 🐛 Issues: GitHub Issues
- 📚 Documentación: [Docs internas]

---

**Desarrollado con ❤️ para Eroski** 🛒