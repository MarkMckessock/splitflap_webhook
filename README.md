# splitflap-webhook

A small Flask service that bridges Twilio SMS to a split-flap display over MQTT. Text a message to your Twilio number and it shows up on the display.

## How it works

Twilio receives an inbound SMS and POSTs it to this service. The service validates the request came from Twilio, sanitizes the text to the characters the display actually supports, and publishes it to an MQTT topic that the display firmware subscribes to.

```
SMS → Twilio → this service → MQTT broker → ESP32 → split-flap display
```

## Supported characters

The display has a fixed character set. Anything outside it is silently dropped:

- `A–Z`, `0–9`
- `. ? - $ ' # , ! @ &`
- Color tiles via lowercase codes: `r` `g` `y` `p` `w` `b`

Messages are truncated to 6 characters (the display width).

### Color emoji shorthand

You can text color square emoji directly — they're automatically converted to their tile codes before publishing:

| Emoji | Code | Color |
|-------|------|-------|
| 🟥 | `r` | Red |
| 🟩 | `g` | Green |
| 🟪 | `p` | Purple |
| 🟨 | `y` | Yellow |
| ⬜ | `w` | White |

## Admin commands

Phone numbers listed in `ADMIN_NUMBERS` can send `/reset` to home all modules.

## Running with Docker

```bash
docker run -d \
  -p 5000:5000 \
  -e MQTT_HOST=192.168.1.100 \
  -e MQTT_TOPIC=home/splitflap/command \
  -e TWILIO_AUTH_TOKEN=your_token \
  -e TWILIO_WEBHOOK_URL=https://your-domain.com/sms \
  ghcr.io/yourusername/splitflap_webhook:latest
```

Or with a `.env` file:

```bash
cp .env.example .env
# fill in .env
docker run -d -p 5000:5000 --env-file .env ghcr.io/yourusername/splitflap_webhook:latest
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MQTT_HOST` | yes | — | MQTT broker hostname or IP |
| `MQTT_PORT` | no | `1883` | MQTT broker port |
| `MQTT_TOPIC` | yes | — | Topic to publish display messages to |
| `MQTT_RESET_TOPIC` | no | `home/splitflap/reset` | Topic that triggers a home/reset |
| `MQTT_USERNAME` | no | — | MQTT username |
| `MQTT_PASSWORD` | no | — | MQTT password |
| `TWILIO_AUTH_TOKEN` | yes | — | From the Twilio console — used to verify webhook signatures |
| `TWILIO_WEBHOOK_URL` | yes | — | Full public URL of the `/sms` endpoint, e.g. `https://example.com/sms` |
| `ADMIN_NUMBERS` | no | — | Comma-separated E.164 numbers that can send `/reset` |
| `ALLOWED_NUMBERS` | no | — | Comma-separated E.164 allowlist. If unset, all senders are accepted |

## Twilio setup

1. Buy a number in the [Twilio console](https://console.twilio.com)
2. Under **Phone Numbers → Manage → Active Numbers**, open the number
3. Set the SMS webhook to `https://your-domain.com/sms` (HTTP POST)
4. Copy your **Auth Token** from the console dashboard into `TWILIO_AUTH_TOKEN`

> **Behind a reverse proxy?** Make sure `TWILIO_WEBHOOK_URL` is the public-facing URL, not `localhost`. Twilio's signature is computed against the URL it actually POSTed to, so they need to match exactly.

## Security

- All requests are verified against Twilio's HMAC-SHA1 signature — unsigned requests are rejected with `403`
- Rate limited to 10 messages/minute and 50/hour per sender
- Optionally restrict to an allowlist of phone numbers via `ALLOWED_NUMBERS`
- Input is sanitized to the display's character set before reaching the broker
