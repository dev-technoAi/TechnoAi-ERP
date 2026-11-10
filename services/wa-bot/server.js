// Techno AI WhatsApp sender.
// Keeps one WhatsApp number linked (like WhatsApp Web) and sends the ERP's RFQ alerts from it.
// It only sends: incoming chats are ignored. It listens on the private Docker network only and
// every call except /health needs the shared key (BOT_KEY), so nothing outside the ERP can use it.
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';

import makeWASocket, {
  Browsers,
  DisconnectReason,
  fetchLatestBaileysVersion,
  jidNormalizedUser,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys';
import pino from 'pino';
import QRCode from 'qrcode';

const PORT = Number(process.env.PORT || 3000);
const BOT_KEY = process.env.BOT_KEY || '';
const AUTH_DIR = process.env.AUTH_DIR || '/data/auth';
const MAX_PER_DAY = Number(process.env.MAX_PER_DAY || 400);
const MIN_GAP_MS = Number(process.env.MIN_GAP_MS || 3000);
const MAX_GAP_MS = Number(process.env.MAX_GAP_MS || 7000);
const MAX_WAIT_MS = 8000; // the ERP waits 10 s per alert; answer before that

if (BOT_KEY.length < 24) {
  console.error('BOT_KEY is missing or shorter than 24 characters; refusing to start.');
  process.exit(1);
}

const state = { status: 'starting', qr: null, me: null, error: null, since: new Date().toISOString() };
const counter = { day: '', sent: 0, failed: 0 };
let sock = null;
let starting = false;
let lastSend = 0;
let qrRounds = 0; // unscanned QR sessions in a row; after 3 the bot waits for "Refresh" instead of looping
let chain = Promise.resolve();

const log = (...args) => console.log(new Date().toISOString(), ...args);
const mask = (digits) => digits.slice(0, 4) + '****' + digits.slice(-3);

function today() {
  const day = new Date().toISOString().slice(0, 10);
  if (counter.day !== day) Object.assign(counter, { day, sent: 0, failed: 0 });
  return counter;
}

async function start() {
  if (starting) return;
  starting = true;
  try {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    let version;
    try {
      ({ version } = await fetchLatestBaileysVersion());
    } catch (error) {
      log('could not fetch the WhatsApp Web version, using the built-in one:', error.message);
    }
    sock = makeWASocket({
      ...(version ? { version } : {}),
      auth,
      logger: pino({ level: 'silent' }),
      browser: Browsers.ubuntu('Techno AI ERP'),
      syncFullHistory: false,
      markOnlineOnConnect: false,
      keepAliveIntervalMs: 30000,
    });
    sock.ev.on('creds.update', saveCreds);
    sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
      if (qr) {
        // WhatsApp gives a few codes, then closes; the bot reconnects and shows a fresh one, so this is not an error
        state.status = 'qr';
        state.error = null;
        state.qr = await QRCode.toDataURL(qr, { margin: 1, width: 320 });
        log('waiting for the QR code to be scanned');
      }
      if (connection === 'open') {
        qrRounds = 0;
        Object.assign(state, { status: 'connected', qr: null, error: null, since: new Date().toISOString(),
                               me: '+' + jidNormalizedUser(sock.user.id).split('@')[0] });
        log('connected as', mask(state.me));
      }
      if (connection === 'close') {
        const code = lastDisconnect?.error?.output?.statusCode;
        starting = false;
        if (code === DisconnectReason.loggedOut) {
          log('the number was logged out; a new QR code will be shown');
          fs.rmSync(AUTH_DIR, { recursive: true, force: true });
          Object.assign(state, { status: 'logged_out', qr: null, me: null, error: 'Logged out from the phone' });
          setTimeout(start, 3000);
        } else if (!sock.authState.creds.registered) {
          // nobody scanned the codes in time: a few fresh rounds, then wait for Refresh in the ERP
          qrRounds += 1;
          if (qrRounds >= 3) {
            Object.assign(state, { status: 'idle', qr: null, error: null });
            log('no scan; waiting for Refresh to show a new code');
          } else {
            Object.assign(state, { status: 'starting', qr: null, error: null });
            setTimeout(start, 1000);
          }
        } else {
          Object.assign(state, { status: 'reconnecting', error: lastDisconnect?.error?.message || 'Connection closed' });
          log('connection closed (%s), reconnecting', code || 'no code');
          setTimeout(start, 5000);
        }
      }
    });
  } catch (error) {
    starting = false;
    Object.assign(state, { status: 'error', error: error.message });
    log('start failed:', error.message);
    setTimeout(start, 15000);
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function deliver(digits, text, ticket) {
  // a short human-like gap between alerts so the number is not flagged as a spammer
  const gap = MIN_GAP_MS + Math.random() * (MAX_GAP_MS - MIN_GAP_MS);
  const wait = lastSend + gap - Date.now();
  if (wait > 0) await sleep(Math.min(wait, MAX_WAIT_MS - 3000));
  if (ticket.expired) return { ok: false, error: 'expired' }; // the ERP was already told "busy": never send late
  const [found] = await sock.onWhatsApp(digits);
  if (!found?.exists) return { ok: false, error: 'This number is not on WhatsApp' };
  const sent = await sock.sendMessage(found.jid, { text });
  lastSend = Date.now();
  return { ok: true, id: sent?.key?.id };
}

function send(digits, text) {
  const ticket = { expired: false };
  const job = chain.then(() => deliver(digits, text, ticket));
  chain = job.catch(() => {});
  const timeout = sleep(MAX_WAIT_MS).then(() => {
    ticket.expired = true;
    return { ok: false, error: 'WhatsApp is busy; try again in a minute' };
  });
  return Promise.race([job, timeout]);
}

function authorised(req) {
  const given = Buffer.from(String(req.headers['x-bot-key'] || ''));
  const wanted = Buffer.from(BOT_KEY);
  return given.length === wanted.length && crypto.timingSafeEqual(given, wanted);
}

function reply(res, code, body) {
  res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  res.end(JSON.stringify(body));
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 20000) reject(new Error('too large'));
    });
    req.on('end', () => {
      try { resolve(JSON.parse(raw || '{}')); } catch (error) { reject(error); }
    });
  });
}

http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://bot');
  if (url.pathname === '/health') return reply(res, 200, { ok: true, status: state.status });
  if (!authorised(req)) return reply(res, 401, { ok: false, error: 'Wrong bot key' });
  try {
    if (req.method === 'GET' && url.pathname === '/status') {
      if (state.status === 'idle') {
        // Refresh in the ERP: start a new linking session and give the first code a moment to arrive
        qrRounds = 0;
        state.status = 'starting';
        start();
        for (let i = 0; i < 12 && state.status !== 'qr'; i++) await sleep(250);
      }
      const day = today();
      return reply(res, 200, { ok: true, ...state, sent_today: day.sent, failed_today: day.failed, max_per_day: MAX_PER_DAY });
    }
    if (req.method === 'POST' && url.pathname === '/send') {
      const body = await readJson(req);
      const digits = String(body.phone || '').replace(/\D/g, '').replace(/^00/, '');
      const text = String(body.message || '').trim();
      if (digits.length < 8 || digits.length > 15) return reply(res, 400, { ok: false, error: 'Use the full number with country code' });
      if (!text || text.length > 4000) return reply(res, 400, { ok: false, error: 'The message is empty or too long' });
      if (state.status !== 'connected') return reply(res, 503, { ok: false, error: 'The WhatsApp number is not connected' });
      const day = today();
      if (day.sent >= MAX_PER_DAY) return reply(res, 429, { ok: false, error: 'Daily limit reached' });
      const result = await send(digits, text);
      if (result.ok) day.sent += 1; else day.failed += 1;
      log(result.ok ? 'sent to' : 'not sent to', mask(digits), result.ok ? '' : result.error);
      return reply(res, result.ok ? 200 : 502, result);
    }
    if (req.method === 'POST' && url.pathname === '/logout') {
      try { await sock?.logout(); } catch (_) { /* already gone */ }
      fs.rmSync(AUTH_DIR, { recursive: true, force: true });
      Object.assign(state, { status: 'logged_out', qr: null, me: null, error: null });
      starting = false;
      setTimeout(start, 2000);
      return reply(res, 200, { ok: true });
    }
    return reply(res, 404, { ok: false, error: 'Not found' });
  } catch (error) {
    log('request failed:', error.message);
    return reply(res, 500, { ok: false, error: 'The bot hit an error' });
  }
}).listen(PORT, () => log('Techno AI WhatsApp sender listening on', PORT));

start();
