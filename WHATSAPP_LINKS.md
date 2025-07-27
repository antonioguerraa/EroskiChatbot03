# Configuración de Enlaces para WhatsApp

## Problema
WhatsApp no convierte automáticamente las URLs de `localhost` en enlaces clickeables porque no son accesibles desde dispositivos móviles.

## Solución

### 1. Configurar URL Pública
Añade a tu archivo `.env`:

```bash
# URL pública accesible desde internet
PUBLIC_URL=https://tu-dominio.com

# O si usas ngrok para desarrollo
PUBLIC_URL=https://abc123.ngrok.io
```

### 2. Opciones para Desarrollo Local

#### Opción A: Usar ngrok (Recomendado para desarrollo)
```bash
# Instalar ngrok
npm install -g ngrok

# Exponer tu servidor local
ngrok http 8000

# Copiar la URL HTTPS que te da ngrok
# Ejemplo: https://abc123.ngrok.io
```

#### Opción B: Usar serveo.net
```bash
ssh -R 80:localhost:8000 serveo.net
```

#### Opción C: Usar localtunnel
```bash
npm install -g localtunnel
lt --port 8000
```

### 3. Formato de Enlaces en WhatsApp

Los enlaces se mostrarán así en WhatsApp:

```
📄 Página 161 (Dibal Mistral):
https://tu-dominio.com/docs/Manual%20Balanza%20DIBAL%20Mistral.pdf#page=161

🖥️ Ver con resaltado:
https://tu-dominio.com/viewer/Manual%20Balanza%20DIBAL%20Mistral.pdf?page=161&highlight=...
```

WhatsApp convertirá automáticamente estas URLs en enlaces clickeables.

### 4. Verificación

Para verificar que está funcionando:

1. Reinicia el servidor después de configurar `PUBLIC_URL`
2. En los logs deberías ver:
   ```
   🌐 OrquestadorBusquedaNode usando URL base: https://tu-dominio.com
   ```
3. Los enlaces en WhatsApp deberían ser clickeables

### 5. Producción

Para producción, necesitarás:
- Un dominio real con HTTPS
- Configurar el servidor web (nginx/apache) para servir los PDFs
- Asegurar que `/docs` y `/viewer` estén accesibles públicamente

### Ejemplo de configuración nginx:
```nginx
server {
    listen 443 ssl;
    server_name tu-dominio.com;
    
    # Servir PDFs
    location /docs/ {
        alias /path/to/your/pdf/files/;
        add_header Content-Type application/pdf;
    }
    
    # Proxy para el viewer
    location /viewer/ {
        proxy_pass http://localhost:8000/viewer/;
    }
}
```