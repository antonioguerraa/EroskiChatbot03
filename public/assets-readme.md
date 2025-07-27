# Public Assets Documentation

This directory contains public assets for the Chainlit application.

## Files:

- `logo_devol.png` - Logo de Eroski/Devol que se muestra en la página de autenticación y en el header del chat
- `eroski-theme.css` - Estilos personalizados para la interfaz de Chainlit con los colores corporativos de Eroski
- `README.md` - Mensaje de bienvenida que se muestra en el chat

## Configuración del logo:

El logo se configura en `.chainlit/config.toml`:
```toml
[UI]
logo = "/public/logo_devol.png"
```

## Ubicación del logo en la interfaz:

1. **Página de autenticación**: Se muestra centrado arriba del formulario de login
2. **Header del chat**: Aparece junto al título de la aplicación

## Estilos personalizados:

Los estilos están definidos en `eroski-theme.css` e incluyen:
- Colores corporativos de Eroski
- Estilización de la página de autenticación
- Personalización del chat
- Estilos específicos para el logo

## Cómo cambiar el logo:

1. Coloca el nuevo logo en esta carpeta (`public/`)
2. Actualiza la ruta en `.chainlit/config.toml`
3. Reinicia la aplicación