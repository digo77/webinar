// ─────────────────────────────────────────────────────────────────────────────
// AutoWebinar — Load Test com k6
// ─────────────────────────────────────────────────────────────────────────────
// Simula participantes entrando na sala, dando heartbeat, chamando /api/events,
// /api/track e /api/user-chat como um usuário real de um webinário ao vivo.
//
// USO:
//   brew install k6     # macOS
//   # ou: https://k6.io/docs/get-started/installation/
//
//   BASE_URL=https://seu-dominio.com SLUG=meu-webinar k6 run tests/loadtest.js
//
// FASES (VUs = usuários virtuais simultâneos):
//   - ramp up 0 → 50 em 30s   (warm up)
//   - hold 50 por 1 min        (smoke)
//   - ramp 50 → 200 em 1 min  (realista)
//   - hold 200 por 2 min      (sustained)
//   - ramp 200 → 500 em 1 min (stress)
//   - hold 500 por 2 min      (pico de lançamento)
//   - ramp down 500 → 0 em 30s
//
// CRITÉRIOS (thresholds k6):
//   - p95 < 800ms no acesso à sala
//   - http_req_failed < 1%
//   - user-chat p95 < 500ms
// ─────────────────────────────────────────────────────────────────────────────

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';
import { randomString, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:5000';
const SLUG = __ENV.SLUG || 'demo';
const SCENARIO = __ENV.SCENARIO || 'full'; // full | quick | spike

const chatLatency = new Trend('chat_post_duration', true);
const heartbeatLatency = new Trend('heartbeat_duration', true);
const salaErrors = new Rate('sala_errors');

// ── Perfis de carga ──────────────────────────────────────────────────────────
const profiles = {
    quick: {
        stages: [
            { duration: '15s', target: 20 },
            { duration: '30s', target: 20 },
            { duration: '10s', target: 0 },
        ],
    },
    full: {
        stages: [
            { duration: '30s', target: 50 },
            { duration: '1m', target: 50 },
            { duration: '1m', target: 200 },
            { duration: '2m', target: 200 },
            { duration: '1m', target: 500 },
            { duration: '2m', target: 500 },
            { duration: '30s', target: 0 },
        ],
    },
    spike: {
        stages: [
            { duration: '10s', target: 500 },
            { duration: '1m', target: 500 },
            { duration: '10s', target: 0 },
        ],
    },
};

export const options = {
    stages: profiles[SCENARIO].stages,
    thresholds: {
        'http_req_duration{scenario:sala}': ['p(95)<800'],
        'http_req_failed': ['rate<0.01'],
        'chat_post_duration': ['p(95)<500'],
        'heartbeat_duration': ['p(95)<300'],
        'sala_errors': ['rate<0.01'],
    },
    // Cookies automáticos
    userAgent: 'k6-loadtest/1.0',
};

// ── Helpers ─────────────────────────────────────────────────────────────────
function randomName() {
    const first = ['Ana', 'João', 'Maria', 'Pedro', 'Carla', 'Lucas', 'Juliana', 'Rafael', 'Beatriz', 'Bruno'];
    const last = ['Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues', 'Lima', 'Costa', 'Alves'];
    return first[Math.floor(Math.random() * first.length)] + ' ' + last[Math.floor(Math.random() * last.length)];
}

function randomPhone() {
    const ddd = randomIntBetween(11, 99);
    const num = '9' + randomIntBetween(10000000, 99999999);
    return `(${ddd}) ${num.slice(0, 5)}-${num.slice(5)}`;
}

// ── Cenário principal: um usuário real na sala ──────────────────────────────
export default function () {
    const jar = http.cookieJar();
    const baseParams = { tags: { scenario: 'sala' } };

    // 1) GET /registrar?w=<slug>
    group('registrar GET', () => {
        const r = http.get(`${BASE_URL}/registrar?w=${SLUG}`, baseParams);
        check(r, { 'registrar 200': (res) => res.status === 200 });
    });

    // 2) POST /registrar (cadastro)
    const name = randomName();
    const phone = randomPhone();
    group('registrar POST', () => {
        const r = http.post(`${BASE_URL}/registrar?w=${SLUG}`, {
            name: name,
            phone_country_code: '+55',
            phone_number: phone,
        }, baseParams);
        const ok = check(r, { 'registrar redirect to sala': (res) => res.status === 200 || res.status === 302 });
        if (!ok) salaErrors.add(1);
    });

    // 3) GET /sala — deveria cair em "waiting" se webinário não está aberto,
    //    ou direto na sala. Ambos são 200.
    group('sala GET', () => {
        const r = http.get(`${BASE_URL}/sala`, baseParams);
        check(r, { 'sala 200/401/400': (res) => [200, 400, 401].includes(res.status) });
    });

    // 4) GET /api/events (timeline)
    group('api events', () => {
        const r = http.get(`${BASE_URL}/api/events`, baseParams);
        check(r, { 'events 200': (res) => res.status === 200 });
    });

    // 5) Loop de ~60s simulando o usuário dentro da sala:
    //    - heartbeat a cada 15s
    //    - track a cada 30s
    //    - eventualmente manda 1-2 mensagens no chat
    const iterations = 4; // ~60s
    for (let i = 0; i < iterations; i++) {
        // Heartbeat
        const hb = http.post(`${BASE_URL}/api/heartbeat`, null, baseParams);
        heartbeatLatency.add(hb.timings.duration);
        check(hb, { 'heartbeat ok': (res) => res.status === 200 || res.status === 401 });

        // Track a cada 2 iterações
        if (i % 2 === 0) {
            http.post(`${BASE_URL}/api/track`, JSON.stringify({ watch_time: (i + 1) * 15 }), {
                headers: { 'Content-Type': 'application/json' },
                tags: { scenario: 'sala' },
            });
        }

        // Chat uma vez só (20% dos usuários)
        if (i === 1 && Math.random() < 0.2) {
            const c = http.post(`${BASE_URL}/api/user-chat`, JSON.stringify({
                message: 'Mensagem teste de carga ' + randomString(10),
            }), {
                headers: { 'Content-Type': 'application/json' },
                tags: { scenario: 'sala' },
            });
            chatLatency.add(c.timings.duration);
            check(c, { 'user-chat 200/401': (res) => [200, 401].includes(res.status) });
        }

        // My-chat poll
        if (i % 2 === 1) {
            http.get(`${BASE_URL}/api/my-chat?since_id=0`, baseParams);
        }

        sleep(15);
    }
}

export function handleSummary(data) {
    return {
        'stdout': textSummary(data),
    };
}

function textSummary(data) {
    const m = data.metrics;
    const line = (label, val) => `  ${label.padEnd(32)} ${val}`;
    return [
        '',
        '─────── AutoWebinar Load Test Summary ───────',
        line('VUs max:', m.vus_max ? m.vus_max.values.max : '-'),
        line('Iterações:', m.iterations ? Math.round(m.iterations.values.count) : '-'),
        line('http_req_duration p95:', m.http_req_duration ? m.http_req_duration.values['p(95)'].toFixed(1) + ' ms' : '-'),
        line('http_req_failed rate:', m.http_req_failed ? (m.http_req_failed.values.rate * 100).toFixed(2) + '%' : '-'),
        line('heartbeat p95:', m.heartbeat_duration ? m.heartbeat_duration.values['p(95)'].toFixed(1) + ' ms' : '-'),
        line('chat POST p95:', m.chat_post_duration ? m.chat_post_duration.values['p(95)'].toFixed(1) + ' ms' : '-'),
        '──────────────────────────────────────────────',
        '',
    ].join('\n');
}
