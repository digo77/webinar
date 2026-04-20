/**
 * AutoWebinar Engine v3 — Modular WebinarEngine
 */
(function () {
    'use strict';

    // ── Nomes brasileiros ─────────────────────────────────────────────────────
    const NOMES_BR = [
        'Ana Paula', 'Maria Clara', 'Juliana', 'Fernanda', 'Camila',
        'Patrícia', 'Daniela', 'Mariana', 'Gabriela', 'Beatriz',
        'Larissa', 'Letícia', 'Vanessa', 'Renata', 'Carolina',
        'Amanda', 'Priscila', 'Mônica', 'Sandra', 'Cristina',
        'João', 'Carlos', 'Pedro', 'Lucas', 'Marcos',
        'André', 'Rafael', 'Bruno', 'Felipe', 'Roberto'
    ];
    const SOBRENOMES_BR = [
        'Silva', 'Santos', 'Oliveira', 'Souza', 'Rodrigues',
        'Ferreira', 'Alves', 'Pereira', 'Lima', 'Gomes',
        'Costa', 'Ribeiro', 'Martins', 'Carvalho', 'Almeida',
        'Lopes', 'Sousa', 'Fernandes', 'Vieira', 'Barbosa'
    ];

    // ── Utils ─────────────────────────────────────────────────────────────────
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
    function avatarColor(name) {
        const colors = ['#e74c3c','#e67e22','#c8820a','#2ecc71','#1abc9c','#3498db','#9b59b6','#e91e63','#00bcd4','#4caf50'];
        let hash = 0;
        for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
        return colors[Math.abs(hash) % colors.length];
    }

    // ══════════════════════════════════════════════════════════════════════════
    // WebinarEngine
    // ══════════════════════════════════════════════════════════════════════════
    const WebinarEngine = {
        currentTime: 0,
        events: [],
        firedEvents: new Set(),
        offerActive: false,
        viewerCount: 0,

        async init() {
            await this.loadEvents();
            if (window.WEBINAR_PREVIEW) {
                this.startPreviewTimer();
            } else {
                this.startVturbListener();
            }
            this.Viewers.startAnimation();
            this.Chatbot.init();
            this.Tracking.init();
            this.Presence.start();
            this.MyChat.start();
            switchTab('chat');
        },

        // Timer controlado para modo preview — ignora VTurb, permite seek via botões
        startPreviewTimer() {
            const self = this;
            let lastTick = Date.now();
            self.previewPaused = false;

            setInterval(function () {
                if (self.previewPaused) { lastTick = Date.now(); return; }
                const now = Date.now();
                const dt = (now - lastTick) / 1000;
                lastTick = now;
                self.currentTime += dt;
                self.tick(self.currentTime);
                const nowEl = document.getElementById('preview-now');
                if (nowEl) {
                    const m = Math.floor(self.currentTime / 60);
                    const s = String(Math.floor(self.currentTime % 60)).padStart(2, '0');
                    nowEl.textContent = m + ':' + s;
                }
            }, 250);

            // Botões "Pular pra X"
            document.addEventListener('click', function (e) {
                const btn = e.target.closest('.preview-skip');
                if (!btn) return;
                const sec = parseInt(btn.dataset.sec) || 0;
                self.seekTo(sec);
            });
        },

        // Reseta firedEvents e re-dispara tudo até `sec`
        seekTo(sec) {
            this.currentTime = sec;
            // Re-sincroniza: marca como fired tudo que já ocorreu, limpa chat visível
            this.firedEvents = new Set();
            const chatBox = document.getElementById('chat-box');
            if (chatBox) chatBox.innerHTML = '';
            // Marca instantaneamente os eventos anteriores para NÃO refirar
            for (const evt of this.events) {
                if (evt.trigger_second < sec - 1) {
                    this.firedEvents.add(evt.id);
                }
            }
            // Os eventos entre sec-1 e sec disparam normalmente no próximo tick
        },

        async loadEvents() {
            try {
                const qs = window.WEBINAR_ID ? '?webinar_id=' + window.WEBINAR_ID : '';
                const resp = await fetch('/api/events' + qs);
                this.events = await resp.json();
                this.events.sort((a, b) => a.trigger_second - b.trigger_second);

                // Auto-injeta cta_popup no pitch_second se não houver evento manual
                const pitchSec = (window.WEBINAR_CONFIG || {}).pitchSecond || 0;
                if (pitchSec > 0) {
                    const hasManualCta = this.events.some(e => e.event_type === 'cta_popup');
                    if (!hasManualCta) {
                        this.events.push({
                            id: '__pitch_auto__',
                            trigger_second: pitchSec,
                            event_type: 'cta_popup',
                            payload: { countdown_minutes: 20 }
                        });
                        this.events.sort((a, b) => a.trigger_second - b.trigger_second);
                    }
                }
            } catch (e) {
                console.error('[WebinarEngine] Erro ao carregar eventos:', e);
            }
        },

        startVturbListener() {
            let vturbResponding = false;
            const self = this;

            window.addEventListener('message', function (e) {
                if (!e.data || typeof e.data !== 'object') return;
                let t = null;
                if (e.data.event === 'timeupdate' && typeof e.data.currentTime === 'number') t = e.data.currentTime;
                if (e.data.type === 'timeupdate' && typeof e.data.time === 'number') t = e.data.time;
                if (e.data.type === 'timeupdate' && typeof e.data.currentTime === 'number') t = e.data.currentTime;
                if (t !== null) {
                    vturbResponding = true;
                    self.currentTime = t;
                    self.tick(t);
                }
                if (e.data.event === 'ended' || e.data.type === 'ended') {
                    self.Offer.showEndBroadcast();
                }
            });

            // Fallback: timer local se VTurb não responder em 10s
            setTimeout(function () {
                if (!vturbResponding) {
                    console.log('[WebinarEngine] Fallback timer ativado');
                    const start = Date.now();
                    setInterval(function () {
                        if (vturbResponding) return;
                        self.currentTime = (Date.now() - start) / 1000;
                        self.tick(self.currentTime);
                    }, 1000);
                }
            }, 10000);
        },

        tick(second) {
            for (const evt of this.events) {
                if (this.firedEvents.has(evt.id)) continue;
                if (second >= evt.trigger_second) {
                    this.firedEvents.add(evt.id);
                    this.fireEvent(evt);
                }
            }
        },

        fireEvent(evt) {
            const p = evt.payload || {};
            const self = this;
            switch (evt.event_type) {
                case 'chat':
                    setTimeout(function () {
                        self.Chat.addMessage(p.author || 'Participante', p.message || '');
                    }, randomBetween(0, 3000));
                    break;

                case 'purchase_notification':
                    // Exibe nomes do payload (legado)
                    if (Array.isArray(p.names)) {
                        p.names.forEach(function (name, i) {
                            setTimeout(function () {
                                self.Chat.addPurchaseBanner(name);
                            }, i * randomBetween(15000, 30000));
                        });
                    }
                    break;

                case 'cta_popup':
                    self.Offer.activate(p.countdown_minutes || 20);
                    break;

                case 'end_broadcast':
                    self.Offer.showEndBroadcast();
                    break;

                case 'poll':
                    // Implementação futura
                    break;
            }
        },

        // ── Chat ──────────────────────────────────────────────────────────────
        Chat: {
            get box() { return document.getElementById('chat-box'); },
            _stickToBottom: true,
            _unseen: 0,
            _listenerAttached: false,

            _attachScrollListener() {
                if (this._listenerAttached) return;
                const box = this.box;
                if (!box) return;
                const self = this;
                box.addEventListener('scroll', function () {
                    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 60;
                    self._stickToBottom = nearBottom;
                    if (nearBottom) self._clearUnseen();
                }, { passive: true });
                this._listenerAttached = true;
            },

            _bumpUnseen() {
                this._unseen++;
                const chip = document.getElementById('chat-new-chip');
                const count = document.getElementById('chat-new-count');
                if (chip && count) {
                    count.textContent = this._unseen;
                    chip.querySelector('span#chat-new-count').nextSibling &&
                        (chip.innerHTML = '↓ <span id="chat-new-count">' + this._unseen + '</span> nova' + (this._unseen > 1 ? 's' : ''));
                    chip.classList.add('show');
                }
            },

            _clearUnseen() {
                this._unseen = 0;
                const chip = document.getElementById('chat-new-chip');
                if (chip) chip.classList.remove('show');
            },

            addMessage(author, message, isUser) {
                const box = this.box;
                if (!box) return;
                this._attachScrollListener();
                const div = document.createElement('div');
                div.className = 'chat-msg';
                const color = isUser ? 'var(--accent-gold)' : avatarColor(author);
                const initial = author.charAt(0).toUpperCase();
                div.innerHTML =
                    '<div style="display:flex;gap:10px;align-items:flex-start">' +
                        '<div style="width:32px;height:32px;border-radius:50%;background:' + color + ';display:flex;align-items:center;justify-content:center;font-family:Montserrat,sans-serif;font-size:12px;font-weight:700;color:#fff;flex-shrink:0">' + escHtml(initial) + '</div>' +
                        '<div style="flex:1;min-width:0">' +
                            '<span style="font-family:Montserrat,sans-serif;font-size:12px;font-weight:700;color:var(--accent-gold)">' + escHtml(author) + '</span>' +
                            '<p style="font-family:Lato,sans-serif;font-size:13px;color:var(--text-primary);margin:2px 0 0;line-height:1.45;word-wrap:break-word">' + escHtml(message) + '</p>' +
                        '</div>' +
                    '</div>';
                box.appendChild(div);
                // Poda do DOM: mantém no máximo 80 msgs pra não travar
                while (box.children.length > 80) box.removeChild(box.firstChild);
                if (isUser || this._stickToBottom) {
                    this.scrollToBottom();
                    this._clearUnseen();
                } else {
                    this._bumpUnseen();
                }
            },

            addAdminReply(message) {
                const box = this.box;
                if (!box) return;
                const div = document.createElement('div');
                div.className = 'chat-msg admin-reply';
                div.innerHTML =
                    '<div style="display:flex;gap:8px;align-items:flex-start;background:rgba(34,197,94,.08);border-left:3px solid #16a34a;border-radius:6px;padding:8px 10px">' +
                        '<div style="width:28px;height:28px;border-radius:50%;background:#16a34a;display:flex;align-items:center;justify-content:center;font-family:Montserrat,sans-serif;font-size:11px;font-weight:700;color:#fff;flex-shrink:0">👤</div>' +
                        '<div style="flex:1;min-width:0">' +
                            '<span style="font-family:Montserrat,sans-serif;font-size:11px;font-weight:700;color:#16a34a">Equipe · Resposta pra você</span>' +
                            '<p style="font-family:Lato,sans-serif;font-size:13px;color:var(--text-primary);margin:2px 0 0;line-height:1.4">' + escHtml(message) + '</p>' +
                        '</div>' +
                    '</div>';
                box.appendChild(div);
                this.scrollToBottom();
            },

            addPurchaseBanner(name) {
                const box = this.box;
                if (!box) return;
                // Remove banner anterior se existir
                const old = box.querySelector('.purchase-banner');
                if (old) {
                    old.style.transition = 'opacity 0.3s';
                    old.style.opacity = '0';
                    setTimeout(function () { if (old.parentNode) old.remove(); }, 300);
                }
                const div = document.createElement('div');
                div.className = 'purchase-banner';
                div.innerHTML =
                    '<span style="font-size:14px">⭐</span>' +
                    '<span style="font-family:Montserrat,sans-serif;font-size:11px;font-weight:600;color:#8a6010">' +
                        escHtml(name) + ' acabou de garantir sua vaga!' +
                    '</span>';
                box.appendChild(div);
                this.scrollToBottom();
                // Remove após 4 segundos
                setTimeout(function () {
                    if (div.parentNode) {
                        div.style.transition = 'opacity 0.5s ease';
                        div.style.opacity = '0';
                        setTimeout(function () { if (div.parentNode) div.remove(); }, 500);
                    }
                }, 4000);
            },

            scrollToBottom() {
                const box = this.box;
                if (!box) return;
                // Smooth se já perto, jump se longe (evita animação enorme)
                const distance = box.scrollHeight - box.scrollTop - box.clientHeight;
                if (distance < 300) {
                    box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
                } else {
                    box.scrollTop = box.scrollHeight;
                }
            }
        },

        // ── Offer ─────────────────────────────────────────────────────────────
        Offer: {
            active: false,
            _cdInterval: null,

            activate(countdownMinutes) {
                if (this.active) return;
                this.active = true;
                WebinarEngine.offerActive = true;

                // Mostra aba oferta com badge pulsante
                const tabOffer = document.getElementById('tab-offer');
                if (tabOffer) {
                    tabOffer.style.display = '';
                    tabOffer.classList.add('tab-offer-active');
                }
                switchTab('offer');

                // Mostra rodapé
                this.showFooterCTA();

                // Countdown
                this.startCountdown(countdownMinutes);

                // Inicia loop de banners de compra
                WebinarEngine.Purchases.startLoop();
            },

            startCountdown(minutes) {
                let remaining = minutes * 60;
                const update = function () {
                    if (remaining <= 0) {
                        clearInterval(WebinarEngine.Offer._cdInterval);
                        document.querySelectorAll('.offer-countdown-display').forEach(function (el) {
                            el.textContent = 'Encerrado!';
                        });
                        const footer = document.getElementById('offer-footer');
                        if (footer) footer.style.display = 'none';
                        return;
                    }
                    const txt = fmtTime(remaining);
                    document.querySelectorAll('.offer-countdown-display').forEach(function (el) {
                        el.textContent = txt;
                    });
                    remaining--;
                };
                update();
                this._cdInterval = setInterval(update, 1000);
            },

            showFooterCTA() {
                const footer = document.getElementById('offer-footer');
                if (footer) footer.style.display = 'flex';
            },

            showEndBroadcast() {
                const el = document.getElementById('broadcast-end');
                if (el) el.style.display = 'flex';
            }
        },

        // ── Viewers ───────────────────────────────────────────────────────────
        Viewers: {
            current: 47,
            startAnimation() {
                const cfg = window.WEBINAR_CONFIG;
                this.current = (cfg && cfg.attendeeBase) || 47;
                const el = document.getElementById('viewer-count');
                if (el) el.textContent = this.current;
                const self = this;
                const tick = function () {
                    const delta = Math.floor(Math.random() * 7) - 3; // -3 a +3
                    self.current = Math.max(10, self.current + delta);
                    if (el) el.textContent = self.current;
                    setTimeout(tick, randomBetween(8000, 15000));
                };
                setTimeout(tick, randomBetween(8000, 15000));
            }
        },

        // ── Purchases ─────────────────────────────────────────────────────────
        Purchases: {
            _running: false,
            generateName() {
                const nome = NOMES_BR[Math.floor(Math.random() * NOMES_BR.length)];
                const sobrenome = SOBRENOMES_BR[Math.floor(Math.random() * SOBRENOMES_BR.length)];
                return nome + ' ' + sobrenome;
            },
            startLoop() {
                if (this._running) return;
                this._running = true;
                const self = this;
                const loop = function () {
                    if (!self._running) return;
                    WebinarEngine.Chat.addPurchaseBanner(self.generateName());
                    setTimeout(loop, randomBetween(20000, 45000));
                };
                setTimeout(loop, randomBetween(5000, 15000));
            }
        },

        // ── Chatbot ───────────────────────────────────────────────────────────
        Chatbot: {
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
                        setTimeout(function () {
                            WebinarEngine.Chat.addMessage('Equipe', r.response, false);
                        }, randomBetween(2000, 4000));
                        break;
                    }
                }
            }
        },

        // ── Presence (heartbeat real) ─────────────────────────────────────────
        Presence: {
            start() {
                const ping = function () {
                    fetch('/api/heartbeat', { method: 'POST' }).catch(function () {});
                };
                ping();
                setInterval(ping, 15000);
                // Pulso extra ao voltar do background (mobile)
                document.addEventListener('visibilitychange', function () {
                    if (!document.hidden) ping();
                });
            }
        },

        // ── My Chat (mensagens reais do usuário + respostas do admin) ─────────
        MyChat: {
            lastId: 0,
            sentLocalIds: new Set(),
            async send(message) {
                try {
                    const resp = await fetch('/api/user-chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: message })
                    });
                    const data = await resp.json();
                    if (data.ok && data.id) {
                        this.sentLocalIds.add(data.id);
                        if (data.id > this.lastId) this.lastId = data.id;
                    }
                } catch (e) {}
            },
            async poll() {
                try {
                    const resp = await fetch('/api/my-chat?since_id=' + this.lastId);
                    const msgs = await resp.json();
                    for (const m of msgs) {
                        if (m.id > this.lastId) this.lastId = m.id;
                        // Se o admin respondeu, mostra como mensagem da equipe
                        if (m.admin_reply && !this.sentLocalIds.has('reply-' + m.id)) {
                            this.sentLocalIds.add('reply-' + m.id);
                            WebinarEngine.Chat.addAdminReply(m.admin_reply);
                        }
                    }
                } catch (e) {}
            },
            start() {
                const self = this;
                setInterval(function () { self.poll(); }, 10000);
                setTimeout(function () { self.poll(); }, 3000);
            }
        },

        // ── Tracking ──────────────────────────────────────────────────────────
        Tracking: {
            init() {
                const self = WebinarEngine;
                setInterval(function () {
                    if (self.currentTime > 0) {
                        fetch('/api/track', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ watch_time: Math.floor(self.currentTime) })
                        }).catch(function () {});
                    }
                }, 30000);
            },
            sendCTAClick() {
                fetch('/api/track', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        watch_time: Math.floor(WebinarEngine.currentTime),
                        clicked_cta: true
                    })
                }).catch(function () {});
            }
        }
    };

    // ── UI global ─────────────────────────────────────────────────────────────
    window.switchTab = function (tab) {
        ['chat', 'support', 'offer'].forEach(function (t) {
            const panel = document.getElementById('panel-' + t);
            const btn = document.getElementById('tab-' + t);
            if (panel) panel.style.display = (t === tab ? 'flex' : 'none');
            if (btn) btn.classList.toggle('active', t === tab);
        });
    };

    window.scrollChatToBottom = function () {
        WebinarEngine.Chat._stickToBottom = true;
        WebinarEngine.Chat.scrollToBottom();
        WebinarEngine.Chat._clearUnseen();
    };

    window.sendUserChat = function () {
        const input = document.getElementById('user-chat-input');
        if (!input) return;
        const msg = input.value.trim();
        if (!msg) return;
        WebinarEngine.Chat.addMessage('Você', msg, true);
        WebinarEngine.MyChat.send(msg);
        WebinarEngine.Chatbot.check(msg);
        input.value = '';
    };

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
            console.error('[WebinarEngine] Erro ao enviar suporte:', e);
        }
    };

    window.trackCTA = function () {
        WebinarEngine.Tracking.sendCTAClick();
    };

    window.toggleFullscreen = function () {
        const wrap = document.getElementById('video-wrap');
        if (!wrap) return;
        const isFs = document.fullscreenElement || document.webkitFullscreenElement;
        if (!isFs) {
            const fn = wrap.requestFullscreen || wrap.webkitRequestFullscreen;
            if (fn) fn.call(wrap);
        } else {
            const fn = document.exitFullscreen || document.webkitExitFullscreen;
            if (fn) fn.call(document);
        }
    };

    // Enter para enviar no chat
    document.addEventListener('DOMContentLoaded', function () {
        const userInput = document.getElementById('user-chat-input');
        if (userInput) {
            userInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); window.sendUserChat(); }
            });
        }
    });

    // ── Init ─────────────────────────────────────────────────────────────────
    WebinarEngine.init();

})();
