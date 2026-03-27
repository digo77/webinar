/**
 * AutoWebinar Engine v2 — Modular
 */
(function () {
    'use strict';

    // ── Utils ────────────────────────────────────────────────────────────────
    function escHtml(str) {
        const d = document.createElement('div');
        d.textContent = String(str || '');
        return d.innerHTML;
    }
    function fmtTime(sec) {
        const m = Math.floor(sec / 60);
        const s = String(Math.floor(sec % 60)).padStart(2, '0');
        return m + ':' + s;
    }
    function randomBetween(a, b) {
        return a + Math.random() * (b - a);
    }
    // Gera cor de avatar baseada no nome (hash simples)
    function avatarColor(name) {
        const colors = ['#e74c3c','#e67e22','#f1c40f','#2ecc71','#1abc9c','#3498db','#9b59b6','#e91e63','#00bcd4','#4caf50'];
        let hash = 0;
        for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
        return colors[Math.abs(hash) % colors.length];
    }

    // ── Estado global ────────────────────────────────────────────────────────
    let events = [];
    let firedEvents = new Set();
    let currentTime = 0;
    let vturbResponding = false;

    // ── Elementos DOM ────────────────────────────────────────────────────────
    const chatBox = document.getElementById('chat-box');
    const viewerCountEl = document.getElementById('viewer-count');

    // ══════════════════════════════════════════════════════════════════════════
    // ChatEngine
    // ══════════════════════════════════════════════════════════════════════════
    const ChatEngine = {
        addMessage(author, message, isUser) {
            if (!chatBox) return;
            const div = document.createElement('div');
            div.className = 'chat-msg';
            const color = isUser ? '#f5a623' : avatarColor(author);
            const initial = author.charAt(0).toUpperCase();
            const nameColor = isUser ? '#f5a623' : '#c0c0d8';
            div.innerHTML =
                '<div style="display:flex;gap:8px;align-items:flex-start">' +
                    '<div class="chat-avatar" style="background:' + color + ';color:#fff;font-size:11px;font-weight:700;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;flex-shrink:0">' + initial + '</div>' +
                    '<div>' +
                        '<span style="font-size:12px;font-weight:700;color:' + nameColor + '">' + escHtml(author) + '</span>' +
                        '<p style="font-size:13px;color:#d0d0e0;margin:2px 0 0;line-height:1.4">' + escHtml(message) + '</p>' +
                    '</div>' +
                '</div>';
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        },

        addPurchaseBanner(name) {
            if (!chatBox) return;
            const div = document.createElement('div');
            div.className = 'purchase-banner';
            div.innerHTML = '<span style="color:#f5a623;font-weight:700;font-size:13px">⭐ ' + escHtml(name) + ' acabou de garantir sua vaga!</span>';
            chatBox.appendChild(div);
            chatBox.scrollTop = chatBox.scrollHeight;
        }
    };

    // ══════════════════════════════════════════════════════════════════════════
    // OfferEngine
    // ══════════════════════════════════════════════════════════════════════════
    const OfferEngine = {
        countdownInterval: null,

        activate(countdownMinutes) {
            // Mostra aba oferta
            const tabOffer = document.getElementById('tab-offer');
            if (tabOffer) { tabOffer.style.display = ''; }
            switchTab('offer');

            // Rodapé fixo
            const footer = document.getElementById('offer-footer');
            if (footer) footer.style.display = 'flex';

            // Inicia countdown
            if (countdownMinutes) {
                let remaining = countdownMinutes * 60;
                this.countdownInterval = setInterval(() => {
                    if (remaining <= 0) {
                        clearInterval(this.countdownInterval);
                        const offerCd = document.getElementById('offer-countdown');
                        const footerCd = document.getElementById('footer-countdown');
                        if (offerCd) offerCd.textContent = 'Encerrado!';
                        if (footerCd) footerCd.textContent = 'Encerrado!';
                        if (footer) footer.style.display = 'none';
                        return;
                    }
                    const txt = fmtTime(remaining);
                    const offerCd = document.getElementById('offer-countdown');
                    const footerCd = document.getElementById('footer-countdown');
                    if (offerCd) offerCd.textContent = txt;
                    if (footerCd) footerCd.textContent = txt;
                    remaining--;
                }, 1000);
            }
        },

        showEndBroadcast() {
            const el = document.getElementById('broadcast-end');
            if (el) el.style.display = 'flex';
        }
    };

    // ══════════════════════════════════════════════════════════════════════════
    // ViewerCounter
    // ══════════════════════════════════════════════════════════════════════════
    const ViewerCounter = {
        current: 47,
        init() {
            this.current = (window.WEBINAR_CONFIG && window.WEBINAR_CONFIG.attendeeBase) || 47;
            this.update();
            // Intervalo aleatório entre 8s e 15s
            const tick = () => {
                this.update();
                setTimeout(tick, randomBetween(8000, 15000));
            };
            setTimeout(tick, randomBetween(8000, 15000));
        },
        update() {
            const delta = Math.floor(Math.random() * 7) - 3; // -3 a +3
            this.current = Math.max(this.current - 5, this.current + delta);
            if (viewerCountEl) viewerCountEl.textContent = this.current;
        }
    };

    // ══════════════════════════════════════════════════════════════════════════
    // ChatbotEngine
    // ══════════════════════════════════════════════════════════════════════════
    const ChatbotEngine = {
        responses: [],
        init() {
            const cfg = window.WEBINAR_CONFIG;
            if (cfg && Array.isArray(cfg.chatbotResponses)) {
                this.responses = cfg.chatbotResponses;
            }
        },
        check(message) {
            const msg = message.toLowerCase();
            for (const r of this.responses) {
                if (r.keyword && msg.includes(r.keyword.toLowerCase())) {
                    const delay = randomBetween(2000, 4000);
                    setTimeout(() => {
                        ChatEngine.addMessage('Equipe', r.response, false);
                    }, delay);
                    break;
                }
            }
        }
    };

    // ══════════════════════════════════════════════════════════════════════════
    // TrackingEngine
    // ══════════════════════════════════════════════════════════════════════════
    const TrackingEngine = {
        init() {
            setInterval(() => {
                if (currentTime > 0) {
                    fetch('/api/track', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ watch_time: Math.floor(currentTime) })
                    }).catch(() => {});
                }
            }, 30000);
        },
        trackCTA() {
            fetch('/api/track', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ watch_time: Math.floor(currentTime), clicked_cta: true })
            }).catch(() => {});
        }
    };

    // ══════════════════════════════════════════════════════════════════════════
    // Event Processor
    // ══════════════════════════════════════════════════════════════════════════
    function processEvents(time) {
        for (const evt of events) {
            if (firedEvents.has(evt.id)) continue;
            if (time >= evt.trigger_second) {
                firedEvents.add(evt.id);
                fireEvent(evt);
            }
        }
    }

    function fireEvent(evt) {
        const p = evt.payload || {};
        switch (evt.event_type) {
            case 'chat':
                // Delay aleatório 0-3s para parecer natural
                setTimeout(() => {
                    ChatEngine.addMessage(p.author || 'Participante', p.message || '');
                }, randomBetween(0, 3000));
                break;

            case 'purchase_notification':
                if (Array.isArray(p.names)) {
                    p.names.forEach((name, i) => {
                        setTimeout(() => {
                            ChatEngine.addPurchaseBanner(name);
                        }, i * randomBetween(15000, 30000));
                    });
                }
                break;

            case 'cta_popup':
                OfferEngine.activate(p.countdown_minutes || 30);
                break;

            case 'end_broadcast':
                OfferEngine.showEndBroadcast();
                break;

            case 'poll':
                // Implementação futura
                break;
        }
    }

    // ══════════════════════════════════════════════════════════════════════════
    // VTurb listener + fallback
    // ══════════════════════════════════════════════════════════════════════════
    window.addEventListener('message', function (e) {
        if (!e.data || typeof e.data !== 'object') return;
        let t = null;
        if (e.data.event === 'timeupdate' && typeof e.data.currentTime === 'number') t = e.data.currentTime;
        if (e.data.type === 'timeupdate' && typeof e.data.time === 'number') t = e.data.time;
        if (e.data.type === 'timeupdate' && typeof e.data.currentTime === 'number') t = e.data.currentTime;
        if (t !== null) {
            vturbResponding = true;
            currentTime = t;
            processEvents(currentTime);
        }
        // Fim de vídeo via VTurb
        if (e.data.event === 'ended' || e.data.type === 'ended') {
            OfferEngine.showEndBroadcast();
        }
    });

    // Fallback: incrementa tempo local se VTurb não emitir eventos em 10s
    setTimeout(function () {
        if (!vturbResponding) {
            console.log('[WebinarEngine] Fallback timer ativado');
            const start = Date.now();
            setInterval(function () {
                if (vturbResponding) return;
                currentTime = (Date.now() - start) / 1000;
                processEvents(currentTime);
            }, 1000);
        }
    }, 10000);

    // ══════════════════════════════════════════════════════════════════════════
    // UI: Abas
    // ══════════════════════════════════════════════════════════════════════════
    window.switchTab = function (tab) {
        ['chat', 'support', 'offer'].forEach(t => {
            const panel = document.getElementById('panel-' + t);
            const btn = document.getElementById('tab-' + t);
            if (panel) panel.style.display = (t === tab ? 'flex' : 'none');
            if (btn) btn.classList.toggle('active', t === tab);
        });
    };

    // ══════════════════════════════════════════════════════════════════════════
    // UI: Chat do usuário
    // ══════════════════════════════════════════════════════════════════════════
    window.sendUserChat = function () {
        const input = document.getElementById('user-chat-input');
        if (!input) return;
        const msg = input.value.trim();
        if (!msg) return;
        ChatEngine.addMessage('Você', msg, true);
        ChatbotEngine.check(msg);
        input.value = '';
    };

    // Enter para enviar no chat
    const userInput = document.getElementById('user-chat-input');
    if (userInput) {
        userInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); window.sendUserChat(); }
        });
    }

    // ══════════════════════════════════════════════════════════════════════════
    // UI: Suporte
    // ══════════════════════════════════════════════════════════════════════════
    window.sendSupport = async function () {
        const input = document.getElementById('support-input');
        const status = document.getElementById('support-status');
        if (!input) return;
        const msg = input.value.trim();
        if (!msg) return;
        try {
            await fetch('/api/support', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });
            input.value = '';
            if (status) status.style.display = 'block';
        } catch (e) {
            console.error('Erro ao enviar suporte:', e);
        }
    };

    // ══════════════════════════════════════════════════════════════════════════
    // UI: Tracking CTA
    // ══════════════════════════════════════════════════════════════════════════
    window.trackCTA = function () {
        TrackingEngine.trackCTA();
    };

    // ══════════════════════════════════════════════════════════════════════════
    // Init
    // ══════════════════════════════════════════════════════════════════════════
    async function init() {
        // Carrega eventos
        try {
            const qs = window.WEBINAR_ID ? '?webinar_id=' + window.WEBINAR_ID : '';
            const resp = await fetch('/api/events' + qs);
            events = await resp.json();
            events.sort((a, b) => a.trigger_second - b.trigger_second);
        } catch (e) {
            console.error('[WebinarEngine] Erro ao carregar eventos:', e);
        }

        ViewerCounter.init();
        ChatbotEngine.init();
        TrackingEngine.init();

        // Garante que painel chat está visível
        window.switchTab('chat');
    }

    init();
})();
