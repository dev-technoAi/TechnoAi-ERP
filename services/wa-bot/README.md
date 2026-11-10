# Techno AI WhatsApp bot

Sends the ERP's WhatsApp alerts (RFQ alerts, Task Hub dispatch) from one company WhatsApp
number, linked like WhatsApp Web by scanning a QR code in
**Settings → Task Hub → WhatsApp dispatch → Own number (Techno AI bot)**.

- It only sends. Chats on that number are not read or answered.
- It listens on the private Docker network only; every call except `/health` needs `X-Bot-Key`.
- A 3–7 s gap between alerts and a daily limit (`MAX_PER_DAY`, default 400) keep the number safe.
- The link to WhatsApp is kept in the `/data` volume; unlinking from the ERP or from the phone clears it.

## Server setup (docker compose, next to the ERP)

`.env` (generate once, never print it):

```
WA_BOT_KEY=<openssl rand -base64 36 | tr -d '/+=' | cut -c1-40>
```

`docker-compose.yml`:

```yaml
services:
  web:
    environment:
      - TECHNOAI_WA_BOT_URL=http://wa-bot:3000
      - TECHNOAI_WA_BOT_KEY=${WA_BOT_KEY}
  wa-bot:
    build: ./src/services/wa-bot
    environment:
      - BOT_KEY=${WA_BOT_KEY}
    volumes:
      - wa-bot-data:/data
    restart: unless-stopped
volumes:
  wa-bot-data:
```

No `ports:` entry: the bot must not be reachable from the internet.

## API (for the ERP)

| Call | Does |
| --- | --- |
| `GET /health` | `{ok, status}`, no key |
| `GET /status` | state (`qr`, `connected`, …), QR as a PNG data URL, number, counts |
| `POST /send {phone, message}` | sends one message; `phone` with country code |
| `POST /logout` | unlinks the number and shows a new QR code |
