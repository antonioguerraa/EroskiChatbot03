from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from app.workflows.incidencia_workflow import procesar_mensaje_whatsapp
from dotenv import load_dotenv
from datetime import datetime
import os
import httpx

load_dotenv()
app = FastAPI()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "eroski2024")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

# Middleware para capturar TODAS las peticiones
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now()
    print(f"\n🌐 PETICIÓN RECIBIDA: {request.method} {request.url}")
    print(f"🕐 Timestamp: {start_time}")
    print(f"🔍 Headers: {dict(request.headers)}")
    
    response = await call_next(request)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    print(f"✅ RESPUESTA ENVIADA: {response.status_code} (duración: {duration:.2f}s)")
    
    return response

# Endpoint de prueba
@app.get("/")
async def root():
    return {"message": "Webhook WhatsApp funcionando", "timestamp": datetime.now().isoformat()}

@app.get("/test")
async def test():
    return {
        "server": "funcionando",
        "webhook_url": "/webhook",
        "verify_token": VERIFY_TOKEN,
        "phone_id_configured": bool(PHONE_NUMBER_ID),
        "token_configured": bool(WHATSAPP_TOKEN)
    }

def handle_status_update(value: dict):
    """
    Procesa actualizaciones de estado de mensajes de WhatsApp Business API.
    """
    try:
        status_obj = value["statuses"][0]
        status = status_obj.get("status")
        message_id = status_obj.get("id")
        recipient_id = status_obj.get("recipient_id")
        timestamp = status_obj.get("timestamp")

        print(f"📦 Estado del mensaje {message_id} para {recipient_id}: {status} (enviado {timestamp})")

        # Aquí podrías guardar en base de datos o enviar logs a un servicio externo
        # Ej: guardar_status_en_db(message_id, recipient_id, status, timestamp)

    except Exception as e:
        print(f"❌ Error al procesar status update: {e}")


@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Verificación del webhook de WhatsApp Business API.
    Facebook envía una petición GET con parameters para verificar el webhook.
    """
    params = request.query_params
    
    # Log para debug
    print(f"🔐 Verificación webhook recibida:")
    print(f"   hub.mode: {params.get('hub.mode')}")
    print(f"   hub.verify_token: {params.get('hub.verify_token')}")
    print(f"   hub.challenge: {params.get('hub.challenge')}")
    print(f"   VERIFY_TOKEN esperado: {VERIFY_TOKEN}")
    
    # Verificar todos los parámetros requeridos
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == VERIFY_TOKEN
        and "hub.challenge" in params
    ):
        challenge = params["hub.challenge"]
        print(f"✅ Verificación exitosa. Devolviendo challenge: {challenge}")
        # Facebook espera SOLO el valor del challenge como texto plano
        return PlainTextResponse(content=challenge)
    
    print("❌ Verificación fallida")
    return PlainTextResponse(content="Forbidden", status_code=403)

@app.post("/webhook")
async def handle_whatsapp(request: Request):
    """
    Maneja mensajes entrantes de WhatsApp Business API
    """
    # Log de la petición recibida
    print("\n" + "="*50)
    print("📨 WEBHOOK POST RECIBIDO")
    print(f"🕐 Timestamp: {datetime.now()}")
    print(f"📍 Headers: {dict(request.headers)}")
    
    try:
        body = await request.json()
        print(f"📦 Body completo recibido:")
        print(f"   {body}")
        
        # Verificar estructura básica
        if "entry" not in body:
            print("❌ No se encontró 'entry' en el body")
            return JSONResponse({"status": "ok"})
        
        entry = body.get("entry", [])[0]
        print(f"📋 Entry: {entry}")
        
        if "changes" not in entry:
            print("❌ No se encontró 'changes' en entry")
            return JSONResponse({"status": "ok"})
            
        changes = entry.get("changes", [])[0]
        print(f"🔄 Changes: {changes}")
        
        value = changes.get("value", {})
        print(f"💎 Value: {value}")

        if "messages" in value:
            print("✅ Mensaje de usuario detectado")
            message = value["messages"][0]
            sender = message["from"]
            
            # Verificar si hay texto
            if "text" in message:
                user_message = message["text"]["body"]
                print(f"👤 Mensaje de {sender}: '{user_message}'")
                
                # Procesar mensaje
                print("🤖 Procesando mensaje con el bot...")
                bot_reply = await procesar_mensaje_whatsapp(sender, user_message)
                print(f"🤖 Respuesta del bot: '{bot_reply}'")
                
                # Enviar respuesta
                print("📤 Enviando respuesta...")
                await enviar_mensaje_whatsapp(sender, bot_reply)
                print("✅ Respuesta enviada")
            else:
                print("⚠️ Mensaje sin texto (posiblemente multimedia)")
                
        elif "statuses" in value:
            print("📊 Status update recibido")
            handle_status_update(value)
        else:
            print("📭 Webhook recibido sin mensaje de usuario ni status")
            print(f"🔍 Contenido de value: {value}")

    except Exception as e:
        print(f"❌ Error procesando webhook: {e}")
        import traceback
        print(f"🔥 Traceback: {traceback.format_exc()}")

    print("="*50 + "\n")
    return JSONResponse({"status": "ok"})

async def enviar_mensaje_whatsapp(phone: str, mensaje: str):
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": mensaje}
    }

    async with httpx.AsyncClient() as client:
        await client.post(url, json=payload, headers=headers)

if __name__ == "__main__":
    import uvicorn
    print("🚀 Iniciando servidor de webhook WhatsApp")
    print(f"🔑 Token de verificación: {VERIFY_TOKEN}")
    print("📱 Endpoint: /webhook")
    uvicorn.run(app, host="0.0.0.0", port=8002)
