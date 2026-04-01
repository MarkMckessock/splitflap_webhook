import logging
import os
import re
from functools import wraps
from flask import Flask, abort, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
from flask_limiter import Limiter
import paho.mqtt.publish as publish

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_TOPIC = os.environ["MQTT_TOPIC"]
MQTT_RESET_TOPIC = os.environ.get("MQTT_RESET_TOPIC", "home/splitflap/reset")
MQTT_USERNAME = os.environ.get("MQTT_USERNAME")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD")

TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WEBHOOK_URL = os.environ["TWILIO_WEBHOOK_URL"]

ADMIN_NUMBERS = {
    n.strip()
    for n in os.environ.get("ADMIN_NUMBERS", "").split(",")
    if n.strip()
}

ALLOWED_NUMBERS = {
    n.strip()
    for n in os.environ.get("ALLOWED_NUMBERS", "").split(",")
    if n.strip()
}

auth = None
if MQTT_USERNAME:
    auth = {"username": MQTT_USERNAME, "password": MQTT_PASSWORD}

twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)

limiter = Limiter(
    app=app,
    key_func=lambda: request.form.get("From", request.remote_addr),
    storage_uri="memory://",
)

logger.info("MQTT configured: host=%s port=%d topic=%s auth=%s",
            MQTT_HOST, MQTT_PORT, MQTT_TOPIC, "yes" if auth else "no")
logger.info("Admin numbers: %d, Allowed numbers: %d (0=open)",
            len(ADMIN_NUMBERS), len(ALLOWED_NUMBERS))

COLOR_EMOJI_MAP = {
    "🟥": "r",
    "🟩": "g",
    "🟪": "p",
    "🟨": "y",
    "⬜": "w",
}

# Allowed splitflap characters: A-Z, 0-9, symbols, and lowercase color codes
_ALLOWED_CHARS = re.compile(r"[^A-Z0-9grypwb .?$'#,!@&\-]")


def sanitize_body(text):
    for emoji, letter in COLOR_EMOJI_MAP.items():
        text = text.replace(emoji, letter)
    text = re.sub(_ALLOWED_CHARS, "", text)
    return text[:6]


def validate_twilio_request(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        signature = request.headers.get("X-Twilio-Signature", "")
        if not twilio_validator.validate(TWILIO_WEBHOOK_URL, request.form, signature):
            logger.warning("Invalid Twilio signature from ip=%s", request.remote_addr)
            abort(403)
        return f(*args, **kwargs)
    return decorated


@app.route("/sms", methods=["POST"])
@validate_twilio_request
@limiter.limit("10 per minute; 50 per hour")
def sms_reply():
    sender = request.form.get("From", "unknown")
    body = request.form.get("Body", "")
    logger.info("Received SMS from=%s body=%r", sender, body)

    if ALLOWED_NUMBERS and sender not in ALLOWED_NUMBERS:
        logger.warning("Rejected sender not in allowlist: %s", sender)
        return str(MessagingResponse())

    if body.strip() == "/reset":
        if sender in ADMIN_NUMBERS:
            logger.info("Reset command from admin=%s", sender)
            try:
                publish.single(MQTT_RESET_TOPIC, payload="", hostname=MQTT_HOST, port=MQTT_PORT, auth=auth)
                logger.info("Published reset to MQTT topic=%s", MQTT_RESET_TOPIC)
            except Exception:
                logger.exception("Failed to publish reset to MQTT")
        else:
            logger.warning("Reset command ignored from non-admin sender=%s", sender)
        return str(MessagingResponse())

    body = sanitize_body(body)
    logger.info("Processed body=%r", body)
    try:
        publish.single(MQTT_TOPIC, payload=body, hostname=MQTT_HOST, port=MQTT_PORT, auth=auth)
        logger.info("Published to MQTT topic=%s", MQTT_TOPIC)
    except Exception:
        logger.exception("Failed to publish to MQTT")
    return str(MessagingResponse())


if __name__ == "__main__":
    app.run(debug=True)
