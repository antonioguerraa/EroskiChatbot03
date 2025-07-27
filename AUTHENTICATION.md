# Autenticación y Personalización en Chainlit

## Configuración

La aplicación ahora requiere autenticación para acceder al chatbot. Se han configurado las siguientes credenciales:

### Usuarios por defecto

1. **Admin** (configurable por variables de entorno)
   - Usuario: `admin` (o la variable de entorno `CHAINLIT_USER`)
   - Contraseña: `eroski2024` (o la variable de entorno `CHAINLIT_PASSWORD`)
   - Rol: admin

2. **Supervisor**
   - Usuario: `supervisor`
   - Contraseña: `eroski_supervisor_2024`
   - Rol: user

3. **Operador**
   - Usuario: `operador`
   - Contraseña: `eroski_operador_2024`
   - Rol: user

## Configuración mediante variables de entorno

Puedes personalizar las credenciales del usuario admin añadiendo estas variables a tu archivo `.env`:

```
CHAINLIT_USER=tu_usuario_admin
CHAINLIT_PASSWORD=tu_contraseña_segura
```

## Uso

1. Ejecuta la aplicación:
   ```bash
   uv run chainlit run chainlit_app.py -w
   ```

2. Se mostrará una pantalla de login donde deberás introducir las credenciales.

3. Una vez autenticado, tendrás acceso al chatbot con un mensaje de bienvenida personalizado.

## Información del usuario en la sesión

La información del usuario autenticado se guarda en el estado de la sesión:
- `chainlit_user`: Nombre de usuario
- `user_role`: Rol del usuario (admin/user)

Esta información está disponible durante toda la sesión y se muestra en el debug cuando `CHAINLIT_DEBUG=true`.

## Seguridad

**IMPORTANTE**: En un entorno de producción:
- Las contraseñas deben almacenarse hasheadas en una base de datos
- Implementar políticas de contraseñas fuertes
- Considerar autenticación de dos factores
- Usar HTTPS para todas las comunicaciones
- Implementar límites de intentos de login

## Personalización del Logo

Chainlit busca automáticamente archivos específicos en la carpeta `public/`:

### Archivos de logo requeridos:
- `logo_dark.png` - Logo para el tema oscuro
- `logo_light.png` - Logo para el tema claro
- `favicon.png` - Icono de la pestaña del navegador

Estos archivos ya han sido creados a partir de `logo_devol.png`.

### Ubicación de los logos:
1. **Página de login**: Se muestra automáticamente el logo apropiado según el tema
2. **Header del chat**: Aparece junto al nombre de la aplicación
3. **Favicon**: Se muestra en la pestaña del navegador

### Estilos personalizados
Los estilos CSS personalizados están en `public/eroski-theme.css` y se aplican automáticamente.

### Imagen de fondo para login (opcional)
Puedes agregar una imagen de fondo en la página de login editando `.chainlit/config.toml`:
```toml
[UI]
login_page_image = "/public/background.jpg"
login_page_image_filter = "brightness-50"
```

**Nota**: Si los cambios no aparecen:
1. Detén y reinicia completamente la aplicación
2. Limpia la caché del navegador (Ctrl+F5)
3. Verifica que los archivos estén en la carpeta `public/`