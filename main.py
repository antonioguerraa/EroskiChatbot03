# main.py
#  https://e3b858464925.ngrok-free.app
#https://1df2ab04858e.ngrok-free.app 
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
import os

app = FastAPI()

VERIFY_TOKEN = "eroski2024"  # Usa el mismo que pongas en el panel de Facebook


@app.get("/webhook")
async def verify_webhook(request: Request):
    params = request.query_params
    if (
        params.get("hub.mode") == "subscribe"
        and params.get("hub.verify_token") == VERIFY_TOKEN
        and "hub.challenge" in params
    ):
        return PlainTextResponse(params["hub.challenge"])
    return PlainTextResponse("Unauthorized", status_code=403)



@app.post("/webhook")
async def handle_webhook(request: Request):
    body = await request.json()
    print("📥 Webhook recibido:")
    print(body)

    try:
        entry = body["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]
        if "messages" in value:
            message = value["messages"][0]
            sender = message.get("from")
            text = message.get("text", {}).get("body")
            print(f"📨 Mensaje de {sender}: {text}")
    except Exception as e:
        print("❌ Error procesando webhook:", e)

    return JSONResponse({"status": "ok"})
