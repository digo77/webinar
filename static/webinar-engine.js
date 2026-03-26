/**
 * AutoWebinar Engine
 * Escuta tempo do video VTurb e dispara eventos de timeline (chat, CTA, poll).
 */
(function () {
    'use strict';

    let events = [];
    let firedEvents = new Set();
    let currentTime = 0;
    let trackingInterval = null;
    let viewerInterval = null;
    let vturbResponding = false;
    let fallbackActive = false;
    let fallbackStart = null;

    const chatBox = document.getElementById('chat-box');
    const ctaArea = document.getElementById('cta-area');
    const ctaTitle = document.getElementById('cta-title');
    const ctaCountdown = document.getElementById('cta-countdown');
    const ctaButton = document.getElementById('cta-button');
    const viewerCount = document.getElementById('viewer-count');

    // Carrega eventos da timeline
    async function loadEvents() {
        try {
            const resp = await fetch('/api/events');
            events = await resp.json();
            events.sort((a, b) => a.trigger_second - b.trigger_second);
        } catch (e) {
            console.error('Erro ao carregar eventos:', e);
        }
    }

    // Adiciona mensagem ao chat
    function addChatMessage(author, message) {
        const div = document.createElement('div');
        div.className = 'chat-msg';
        div.innerHTML =
            '<div class="flex gap-2">' +
                '<div class="w-7 h-7 rounded-full bg-gray-700 flex items-center justify-center text-xs font-bold shrink-0">' +
                    author.charAt(0).toUpperCase() +
                '</div>' +
                '<div>' +
                    '<span class="text-xs font-semibold text-blue-400">' + escapeHtml(author) + '</span>' +
                    '<p class="text-sm text-gray-300 mt-0.5">' + escapeHtml(message) + '</p>' +
                '</div>' +
            '</div>';
        chatBox.appendChild(div);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // Mostra popup CTA
    function showCTA(payload) {
        if (!ctaArea) return;
        ctaArea.classList.remove('hidden');
        ctaTitle.textContent = payload.title || 'Oferta Especial';
        ctaButton.href = payload.url || window.WEBINAR_CONFIG.upsellUrl || '#';
        ctaButton.textContent = window.WEBINAR_CONFIG.ctaText || 'Quero aproveitar!';

        // Clique no CTA - tracking
        ctaButton.onclick = function () {
            trackAction('clicked_cta');
        };

        // Countdown do CTA
        if (payload.countdown_minutes) {
            let remaining = payload.countdown_minutes * 60;
            function updateCtaCountdown() {
                if (remaining <= 0) {
                    ctaCountdown.textContent = 'Encerrado!';
                    return;
                }
                const m = Math.floor(remaining / 60);
                const s = remaining % 60;
                ctaCountdown.textContent = String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
                remaining--;
                setTimeout(updateCtaCountdown, 1000);
            }
            updateCtaCountdown();
        }
    }

    // Processa eventos baseado no tempo atual
    function processEvents(time) {
        for (const evt of events) {
            if (firedEvents.has(evt.id)) continue;
            if (time >= evt.trigger_second) {
                firedEvents.add(evt.id);
                switch (evt.event_type) {
                    case 'chat':
                        addChatMessage(evt.payload.author, evt.payload.message);
                        break;
                    case 'cta_popup':
                        showCTA(evt.payload);
                        break;
                    case 'poll':
                        // Poll pode ser implementado futuramente
                        break;
                }
            }
        }
    }

    // Escuta postMessage do VTurb
    window.addEventListener('message', function (e) {
        if (e.data && typeof e.data === 'object') {
            // VTurb envia { event: 'timeupdate', currentTime: X }
            if (e.data.event === 'timeupdate' && typeof e.data.currentTime === 'number') {
                vturbResponding = true;
                currentTime = e.data.currentTime;
                processEvents(currentTime);
            }
            // Tambem aceita formato { type: 'timeupdate', time: X }
            if (e.data.type === 'timeupdate' && typeof e.data.time === 'number') {
                vturbResponding = true;
                currentTime = e.data.time;
                processEvents(currentTime);
            }
        }
    });

    // Fallback: se VTurb nao responder postMessage em 10s, usa setInterval
    function startFallback() {
        if (fallbackActive) return;
        fallbackActive = true;
        fallbackStart = Date.now();
        console.log('VTurb nao respondeu postMessage, ativando fallback por timer');

        setInterval(function () {
            if (vturbResponding) return; // VTurb voltou, para fallback
            currentTime = (Date.now() - fallbackStart) / 1000;
            processEvents(currentTime);
        }, 1000);
    }

    setTimeout(function () {
        if (!vturbResponding) startFallback();
    }, 10000);

    // Contador de participantes animado
    function animateViewerCount() {
        const base = window.WEBINAR_CONFIG.attendeeBase || 47;
        function update() {
            const variation = Math.floor(Math.random() * 7) - 3; // -3 a +3
            const count = Math.max(base - 5, base + variation);
            if (viewerCount) viewerCount.textContent = count;
        }
        update();
        viewerInterval = setInterval(update, 8000 + Math.random() * 7000);
    }

    // Tracking periodico
    function startTracking() {
        trackingInterval = setInterval(function () {
            if (currentTime > 0) {
                fetch('/api/track', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        token: window.WEBINAR_TOKEN,
                        watch_time: Math.floor(currentTime)
                    })
                }).catch(function () {});
            }
        }, 30000); // a cada 30s
    }

    function trackAction(action) {
        const data = { token: window.WEBINAR_TOKEN };
        data[action] = true;
        data.watch_time = Math.floor(currentTime);
        fetch('/api/track', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).catch(function () {});
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Init
    loadEvents();
    animateViewerCount();
    startTracking();
})();
