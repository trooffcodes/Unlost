import json
import base64
import requests
from config import Config

# Optional notifications complete within the request lifecycle.
def _fire_webhook(url, **kwargs):
    if not url:
        return
    try:
        requests.post(url, timeout=3, **kwargs)
    except Exception as e:
        # NOTE: Using print instead of logger.error to prevent infinite loops with the Error Webhook
        print(f"Webhook failed to send ({type(e).__name__})")

def notify_error(error_text: str):
    if not Config.WEBHOOK_ERROR:
        return
    
    payload = {
        "embeds": [{
            "title": "🚨 Application Error Triggered",
            "description": f"```\n{error_text[:4000]}\n```",
            "color": 16711680 # Red
        }]
    }
    _fire_webhook(Config.WEBHOOK_ERROR, json=payload)

def notify_user(device_id: str, metadata: dict):
    if not Config.WEBHOOK_USER:
        return
    
    embed = {
        "title": "👤 New User Registered",
        "color": 3447003, # Blue
        "fields": [
            {"name": "Device ID", "value": f"`{device_id}`", "inline": True},
            {"name": "IP Address", "value": f"`{metadata.get('ip', 'Unknown')}`", "inline": True},
            {"name": "OS", "value": metadata.get("os", "Unknown OS"), "inline": True},
            {"name": "Browser", "value": metadata.get("browser", "Unknown Browser"), "inline": True},
            {"name": "Device Type", "value": metadata.get("device_type", "Unknown"), "inline": True},
            {"name": "Origin URL", "value": metadata.get("current_url", "Unknown"), "inline": False}
        ]
    }
    _fire_webhook(Config.WEBHOOK_USER, json={"embeds": [embed]})

def notify_feedback(device_id: str, message: str, image_data: str, metadata: dict):
    if not Config.WEBHOOK_FEEDBACK:
        return
    
    embed = {
        "title": "📝 New User Feedback",
        "description": message or "*No message provided*",
        "color": 16753920, # Orange
        "fields": [
            {"name": "Device ID", "value": f"`{device_id}`", "inline": True},
            {"name": "IP Address", "value": f"`{metadata.get('ip', 'Unknown')}`", "inline": True},
            {"name": "Resolution", "value": metadata.get("resolution", "Unknown"), "inline": True},
            {"name": "Time on Page", "value": metadata.get("time_on_page", "Unknown"), "inline": True}
        ]
    }
    
    kwargs = {}
    # Convert base64 data URL string into raw bytes and attach it physically to Discord
    if image_data and image_data.startswith("data:image"):
        try:
            header, b64_str = image_data.split(",", 1)
            mime = header.split(";")[0].split(":")[1]
            ext = mime.split("/")[1]
            img_bytes = base64.b64decode(b64_str)
            
            embed["image"] = {"url": f"attachment://screenshot.{ext}"}
            kwargs["data"] = {"payload_json": json.dumps({"embeds": [embed]})}
            kwargs["files"] = {"file": (f"screenshot.{ext}", img_bytes, mime)}
        except Exception as e:
            print(f"Failed decoding feedback image: {e}")
            kwargs["json"] = {"embeds": [embed]}
    else:
        kwargs["json"] = {"embeds": [embed]}
        
    _fire_webhook(Config.WEBHOOK_FEEDBACK, **kwargs)

def notify_file(device_id: str, filename: str, file_bytes: bytes):
    if not Config.WEBHOOK_FILE:
        return
    
    embed = {
        "title": "📁 New File Uploaded",
        "description": f"**File:** `{filename}`\n**Device ID:** `{device_id}`\n**Size:** `{len(file_bytes)} bytes`",
        "color": 5763719 # Green
    }
    
    kwargs = {
        "data": {"payload_json": json.dumps({"embeds": [embed]})},
        "files": {"file": (filename, file_bytes)}
    }
    
    _fire_webhook(Config.WEBHOOK_FILE, **kwargs)