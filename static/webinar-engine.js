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
            this.PublicChat.start();
            switchTab('chat');
            // Pre-popula chat com mensagens de aquecimento + background contínuo
            this.PreloadChat.run();
            this.BackgroundChat.start();
            if (window.WEBINAR_IS_ADMIN) this.AdminInbox.start();
            this.Poll.start();
            this.Reactions.start();
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
                        // Passa o eventId (numero) apenas se o evento veio do banco —
                        // os fakes do PreloadChat/BackgroundChat nao tem id e nao podem ser deletados.
                        const eid = typeof evt.id === 'number' ? evt.id : null;
                        self.Chat.addMessage(p.author || 'Participante', p.message || '', false, eid);
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
                    fetch('/api/session-ended', { method: 'POST' }).catch(function () {});
                    break;

                case 'poll':
                    // Implementação futura
                    break;

                case 'pin_message': {
                    const banner = document.getElementById('pinned-banner');
                    const bannerText = document.getElementById('pinned-banner-text');
                    if (banner && bannerText) {
                        bannerText.textContent = p.message || '';
                        banner.style.display = 'block';
                        const dur = parseInt(p.duration) || 0;
                        if (dur > 0) {
                            setTimeout(function () { banner.style.display = 'none'; }, dur * 1000);
                        }
                    }
                    break;
                }
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

            addMessage(author, message, isUser, eventId, ts, chatMsgId) {
                const box = this.box;
                if (!box) return;
                this._attachScrollListener();
                const div = document.createElement('div');
                div.className = 'chat-msg';
                if (eventId) div.dataset.eventId = eventId;
                if (chatMsgId) div.dataset.chatMsgId = chatMsgId;
                const color = isUser ? 'var(--accent-gold)' : avatarColor(author);
                const initial = author.charAt(0).toUpperCase();
                const tsHtml = ts
                    ? '<span style="font-family:Lato,sans-serif;font-size:10px;color:var(--text-muted);margin-left:5px;font-weight:400">' + escHtml(ts) + '</span>'
                    : '';

                let rightHtml = '';
                if (window.WEBINAR_IS_ADMIN && chatMsgId) {
                    const cid = chatMsgId;
                    const bs = 'background:rgba(30,58,95,.12);border:1px solid rgba(30,58,95,.2);border-radius:5px;padding:2px 5px;font-size:10px;cursor:pointer;line-height:1.3';
                    const ds = 'background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#dc2626;border-radius:5px;padding:2px 5px;font-size:10px;cursor:pointer;line-height:1.3';
                    rightHtml =
                        '<div style="display:flex;flex-direction:column;gap:2px;flex-shrink:0;margin-left:4px">' +
                            '<div style="display:flex;gap:2px">' +
                                '<button class="admin-chat-btn" data-chat-id="' + cid + '" data-action="edit" title="Editar" style="' + bs + '">✏️</button>' +
                                '<button class="admin-chat-btn" data-chat-id="' + cid + '" data-action="pin" title="Fixar" style="' + bs + '">📌</button>' +
                            '</div>' +
                            '<div style="display:flex;gap:2px">' +
                                '<button class="admin-chat-btn" data-chat-id="' + cid + '" data-action="delete" title="Apagar" style="' + ds + '">🗑</button>' +
                                '<button class="admin-chat-btn" data-chat-id="' + cid + '" data-action="unpin" title="Desafixar" style="' + bs + '">📍</button>' +
                            '</div>' +
                        '</div>';
                } else if (window.WEBINAR_IS_ADMIN && eventId && typeof eventId === 'number') {
                    rightHtml = '<button class="chat-delete-btn" data-event-id="' + eventId + '" title="Excluir comentario" style="background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.3);color:#dc2626;border-radius:6px;padding:3px 7px;font-size:11px;cursor:pointer;flex-shrink:0;line-height:1">🗑</button>';
                }

                div.innerHTML =
                    '<div style="display:flex;gap:10px;align-items:flex-start">' +
                        '<div style="width:32px;height:32px;border-radius:50%;background:' + color + ';display:flex;align-items:center;justify-content:center;font-family:Montserrat,sans-serif;font-size:12px;font-weight:700;color:#fff;flex-shrink:0">' + escHtml(initial) + '</div>' +
                        '<div style="flex:1;min-width:0">' +
                            '<span style="font-family:Montserrat,sans-serif;font-size:12px;font-weight:700;color:var(--accent-gold)">' + escHtml(author) + '</span>' +
                            tsHtml +
                            '<p style="font-family:Lato,sans-serif;font-size:13px;color:var(--text-primary);margin:2px 0 0;line-height:1.45;word-wrap:break-word">' + escHtml(message) + '</p>' +
                        '</div>' +
                        rightHtml +
                    '</div>';
                box.appendChild(div);
                // Reset do "silencio" pro BackgroundChat nao competir
                if (WebinarEngine.BackgroundChat) WebinarEngine.BackgroundChat.lastMsgAt = Date.now();
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
                // IMPORTANTE: nunca usar scrollIntoView — ele sobe a pagina inteira
                // (inclusive o video). Rolamos APENAS o container do chat.
                try {
                    box.scrollTo({ top: box.scrollHeight, behavior: 'smooth' });
                } catch (e) {
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
                        const ps = document.querySelector('.panel-section');
                        if (ps) ps.style.paddingBottom = '';
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
                if (!footer) return;
                footer.style.display = 'flex';
                // Empurra o painel pra cima para o footer fixo não cobrir o input de chat
                requestAnimationFrame(function () {
                    const h = footer.getBoundingClientRect().height;
                    const ps = document.querySelector('.panel-section');
                    if (ps) ps.style.paddingBottom = h + 'px';
                });
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

        // ── Pre-populate: só se a timeline começa tarde ──────────────────────
        PreloadChat: {
            saudacoes: [
                'Boa noite pessoal!', 'Oiê, cheguei!', 'Vim direto do trabalho 😅',
                'Até que enfim!', 'Eba, começou!', 'De Porto Alegre aqui 👋',
                'Salvador presente 🧡', 'Manaus chegando', 'Tô ansiosa!',
                'Boa tarde! Aqui de BH', 'Rio de Janeiro ó 🌊', 'Recife presente',
                'Curitiba chegou', 'Brasília tmj', 'Trouxe papel e caneta 📝',
            ],
            run() {
                // Só dispara saudações se o primeiro chat da timeline demora >15s
                const firstChat = (WebinarEngine.events || []).find(function (e) { return e.event_type === 'chat'; });
                if (!firstChat || firstChat.trigger_second < 15) return;

                const n = Math.min(5, Math.floor(firstChat.trigger_second / 3));
                const schedule = [];
                for (let i = 0; i < n; i++) schedule.push(500 + i * 1200);
                const saudacoes = this.saudacoes;
                schedule.forEach(function (delay, idx) {
                    const nome = NOMES_BR[Math.floor(Math.random() * NOMES_BR.length)] + ' ' +
                                 SOBRENOMES_BR[Math.floor(Math.random() * SOBRENOMES_BR.length)];
                    const msg = saudacoes[Math.floor(Math.random() * saudacoes.length)];
                    setTimeout(function () { WebinarEngine.Chat.addMessage(nome, msg); }, delay);
                });
            }
        },

        // ── Background chat: SÓ preenche vazios longos da timeline ──────────
        // Dispara uma msg fake apenas se passarem >25s desde o ultimo
        // comentario (timeline ou fake). Respeita o ritmo da sua timeline.
        BackgroundChat: {
            frases: [
                'Muito bom!', 'Adorando', 'Isso 👏👏', 'Amei a explicação',
                '❤️❤️', 'Massa demais', 'Top', 'Aprendi tanto já', 'Que show',
                'Perfeito', 'Tô anotando tudo', 'Maravilha', 'Entendi agora',
                'Que didática boa', 'Deu fome 🥺', 'Apaixonada por essa receita',
            ],
            _t: null,
            _running: false,
            lastMsgAt: 0,
            SILENCE_SECONDS: 25,  // so dispara fake apos 25s sem nenhuma msg
            markActivity() { this.lastMsgAt = Date.now(); },
            start() {
                if (this._running) return;
                this._running = true;
                this.lastMsgAt = Date.now();
                const self = this;
                const loop = function () {
                    if (!self._running) return;
                    const silenceMs = Date.now() - self.lastMsgAt;
                    if (silenceMs >= self.SILENCE_SECONDS * 1000) {
                        const nome = NOMES_BR[Math.floor(Math.random() * NOMES_BR.length)] + ' ' +
                                     SOBRENOMES_BR[Math.floor(Math.random() * SOBRENOMES_BR.length)];
                        const msg = self.frases[Math.floor(Math.random() * self.frases.length)];
                        WebinarEngine.Chat.addMessage(nome, msg);
                        // addMessage ja chamou markActivity via Chat hook
                    }
                    self._t = setTimeout(loop, randomBetween(8000, 14000));
                };
                setTimeout(loop, 15000);
            },
            stop() {
                this._running = false;
                if (this._t) clearTimeout(this._t);
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
            lastReplyCheckedAt: null,
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
                    const now = new Date().toISOString();
                    let url = '/api/my-chat?since_id=' + this.lastId;
                    if (this.lastReplyCheckedAt) {
                        url += '&replied_since=' + encodeURIComponent(this.lastReplyCheckedAt);
                    }
                    const resp = await fetch(url);
                    const msgs = await resp.json();
                    for (const m of msgs) {
                        if (m.id > this.lastId) this.lastId = m.id;
                        // Mostra resposta do admin (funciona mesmo em mensagens antigas)
                        if (m.admin_reply && !this.sentLocalIds.has('reply-' + m.id)) {
                            this.sentLocalIds.add('reply-' + m.id);
                            WebinarEngine.Chat.addAdminReply(m.admin_reply);
                        }
                    }
                    this.lastReplyCheckedAt = now;
                } catch (e) {}
            },
            start() {
                const self = this;
                setInterval(function () { self.poll(); }, 10000);
                setTimeout(function () { self.poll(); }, 3000);
            }
        },

        // ── Public Chat (mensagens aprovadas pelo admin) ──────────────────────
        PublicChat: {
            lastId: 0,
            pinnedId: null,
            async poll() {
                try {
                    const wid = window.WEBINAR_ID || '';
                    const ss = window.WEBINAR_SESSION_START ? encodeURIComponent(window.WEBINAR_SESSION_START) : '';
                    const ssParam = ss ? '&session_start=' + ss : '';
                    const resp = await fetch('/api/public-chat?webinar_id=' + wid + '&since_id=' + this.lastId + ssParam);
                    const data = await resp.json();
                    // Novas mensagens aprovadas
                    for (const m of (data.messages || [])) {
                        if (m.id > this.lastId) this.lastId = m.id;
                        const chatMsgId = (window.WEBINAR_IS_ADMIN && m.is_equipe) ? m.id : null;
                        WebinarEngine.Chat.addMessage(m.name || 'Participante', m.message || '', false, null, m.ts || null, chatMsgId);
                        if (m.admin_reply) {
                            setTimeout(function() {
                                WebinarEngine.Chat.addAdminReply(m.admin_reply);
                            }, 800);
                        }
                    }
                    // Comentário fixado
                    const pinned = data.pinned;
                    if (pinned && pinned.id !== this.pinnedId) {
                        this.pinnedId = pinned.id;
                        this._showPinned(pinned);
                    } else if (!pinned && this.pinnedId) {
                        this.pinnedId = null;
                        const el = document.getElementById('chat-pinned-banner');
                        if (el) el.remove();
                    }
                } catch(e) {}
            },
            _showPinned(pinned) {
                const box = document.getElementById('chat-box');
                if (!box) return;
                let el = document.getElementById('chat-pinned-banner');
                if (!el) {
                    el = document.createElement('div');
                    el.id = 'chat-pinned-banner';
                    el.style.cssText = 'position:sticky;top:0;z-index:10;background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.3);border-radius:8px;padding:8px 12px;margin-bottom:8px;font-family:Lato,sans-serif;font-size:12px;color:var(--text-primary);line-height:1.4';
                    box.parentNode.insertBefore(el, box);
                }
                const esc = function(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); };
                const unpinBtn = window.WEBINAR_IS_ADMIN
                    ? '<button onclick="adminUnpin(' + pinned.id + ')" style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.25);color:#dc2626;border-radius:5px;padding:2px 8px;font-size:11px;cursor:pointer;font-family:Montserrat,sans-serif;font-weight:700;white-space:nowrap;flex-shrink:0">✕ Desafixar</button>'
                    : '';
                el.innerHTML =
                    '<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">' +
                        '<div style="flex:1;min-width:0">' +
                            '<span style="font-family:Montserrat,sans-serif;font-size:10px;font-weight:700;color:var(--accent-gold);display:block;margin-bottom:2px">📌 Mensagem fixada</span>' +
                            esc(pinned.message) +
                        '</div>' +
                        unpinBtn +
                    '</div>';
            },
            start() {
                if (window.WEBINAR_PREVIEW) return;
                const self = this;
                setTimeout(function() { self.poll(); }, 2000);
                setInterval(function() { self.poll(); }, 4000);
            }
        },

        // ── Enquete ao vivo ───────────────────────────────────────────────────
        Poll: {
            _activePollId: null,
            _interval: null,

            start() {
                if (window.WEBINAR_PREVIEW) return;
                const self = this;
                setTimeout(function () { self.fetch(); }, 2000);
                self._interval = setInterval(function () { self.fetch(); }, 4000);
            },

            async fetch() {
                const wid = window.WEBINAR_ID;
                if (!wid) return;
                try {
                    const r = await fetch('/api/poll/' + wid);
                    const data = await r.json();
                    this._render(data);
                } catch (e) {}
            },

            async vote(pollId, optionIndex) {
                try {
                    await fetch('/api/poll/' + pollId + '/vote', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ option_index: optionIndex })
                    });
                    await this.fetch();
                } catch (e) {}
            },

            async closeAdmin(pollId) {
                if (!confirm('Encerrar enquete?')) return;
                try {
                    await fetch('/admin/api/poll/' + pollId + '/close', { method: 'POST' });
                    await this.fetch();
                } catch (e) {}
            },

            _render(data) {
                const widget = document.getElementById('poll-widget');
                if (!widget) return;
                if (!data) {
                    widget.style.display = 'none';
                    this._activePollId = null;
                    return;
                }
                this._activePollId = data.id;
                widget.style.display = 'block';
                const total = data.total || 0;
                const voted = data.my_vote !== null && data.my_vote !== undefined;
                const isAdmin = window.WEBINAR_IS_ADMIN;

                let html = '<div style="font-family:Montserrat,sans-serif;font-size:10px;font-weight:700;color:var(--accent-gold);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">📊 Enquete ao vivo</div>';
                html += '<p style="font-family:Lato,sans-serif;font-size:13px;font-weight:700;color:var(--text-primary);margin:0 0 10px;line-height:1.35">' + escHtml(data.question) + '</p>';

                if (!voted) {
                    // Botões de votação
                    html += '<div style="display:flex;flex-direction:column;gap:6px">';
                    data.options.forEach(function (opt, i) {
                        html += '<button class="poll-opt-btn" onclick="WebinarEngine.Poll.vote(' + data.id + ',' + i + ')">' + escHtml(opt) + '</button>';
                    });
                    html += '</div>';
                } else {
                    // Resultados
                    html += '<div style="display:flex;flex-direction:column;gap:8px">';
                    data.options.forEach(function (opt, i) {
                        const count = data.counts[i] || 0;
                        const pct = total > 0 ? Math.round(count / total * 100) : 0;
                        const isMyVote = data.my_vote === i;
                        html += '<div>' +
                            '<div style="display:flex;justify-content:space-between;font-family:Lato,sans-serif;font-size:12px;margin-bottom:3px">' +
                                '<span style="color:' + (isMyVote ? 'var(--accent-gold)' : 'var(--text-primary)') + ';font-weight:' + (isMyVote ? '700' : '400') + '">' + escHtml(opt) + (isMyVote ? ' ✓' : '') + '</span>' +
                                '<span style="color:var(--text-muted);font-size:11px">' + pct + '% (' + count + ')</span>' +
                            '</div>' +
                            '<div class="poll-bar"><div class="poll-bar-fill" style="width:' + pct + '%"></div></div>' +
                        '</div>';
                    });
                    html += '</div>';
                }

                html += '<div style="font-family:Lato,sans-serif;font-size:10px;color:var(--text-muted);margin-top:8px">' + total + ' voto' + (total !== 1 ? 's' : '') + '</div>';

                if (isAdmin) {
                    html += '<button onclick="WebinarEngine.Poll.closeAdmin(' + data.id + ')" style="margin-top:8px;background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.25);color:#dc2626;border-radius:6px;padding:4px 10px;font-family:Montserrat,sans-serif;font-weight:700;font-size:10px;cursor:pointer">🔚 Encerrar enquete</button>';
                }

                widget.innerHTML = html;
            }
        },

        // ── Reações flutuantes ────────────────────────────────────────────────
        Reactions: {
            _lastTs: null,
            _interval: null,
            _lastSent: 0,
            RATE_MS: 1500,

            start() {
                if (window.WEBINAR_PREVIEW) return;
                const self = this;
                self._interval = setInterval(function () { self.fetchRemote(); }, 2500);
            },

            send(emoji) {
                const now = Date.now();
                if (now - this._lastSent < this.RATE_MS) return;
                this._lastSent = now;
                this._float(emoji, true);
                fetch('/api/react', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ emoji: emoji })
                }).catch(function () {});
            },

            async fetchRemote() {
                const wid = window.WEBINAR_ID;
                if (!wid) return;
                try {
                    const url = '/api/reactions/' + wid + (this._lastTs ? '?since=' + encodeURIComponent(this._lastTs) : '');
                    const r = await fetch(url);
                    const data = await r.json();
                    this._lastTs = data.ts;
                    const counts = data.counts || {};
                    Object.entries(counts).forEach(function ([emoji, count]) {
                        const n = Math.min(parseInt(count) || 0, 5);
                        for (let i = 0; i < n; i++) {
                            setTimeout(function () {
                                WebinarEngine.Reactions._float(emoji, false);
                            }, i * 200);
                        }
                    });
                } catch (e) {}
            },

            _float(emoji, fromButton) {
                const wrap = document.getElementById('reaction-floats');
                if (!wrap) return;
                const parent = wrap.parentElement;
                const w = parent ? parent.clientWidth : 300;
                const el = document.createElement('div');
                el.className = 'react-float';
                const x = fromButton
                    ? (w - 50) + (Math.random() - 0.5) * 30  // perto dos botões (direita)
                    : 30 + Math.random() * (w - 80);           // posição aleatória
                const rot = (Math.random() - 0.5) * 28 + 'deg';
                el.style.cssText = 'left:' + x + 'px;bottom:50px;--rot:' + rot;
                el.textContent = emoji;
                wrap.appendChild(el);
                setTimeout(function () { el.remove(); }, 1700);
            }
        },

        // ── Admin Inbox Drawer ────────────────────────────────────────────────
        AdminInbox: {
            _msgs: [],
            _pendingCount: 0,
            _interval: null,
            _isOpen: false,

            start() {
                const self = this;
                document.addEventListener('keydown', function (e) {
                    if (e.key === 'Escape' && self._isOpen) self.close();
                });
                self.poll();
                self._interval = setInterval(function () { self.poll(); }, 5000);
            },

            async poll() {
                const wid = window.WEBINAR_ID;
                if (!wid) return;
                try {
                    const r = await fetch('/admin/api/webinar/' + wid + '/inbox');
                    this._msgs = await r.json();
                    const pending = this._msgs.filter(function (m) { return m.status === 'pending'; }).length;
                    if (pending !== this._pendingCount) {
                        this._pendingCount = pending;
                        this._updateBadge(pending);
                    }
                    if (this._isOpen) this._render();
                } catch (e) {}
            },

            _updateBadge(count) {
                const badge = document.getElementById('admin-inbox-badge');
                const btn = document.getElementById('admin-inbox-btn');
                if (!badge) return;
                if (count > 0) {
                    badge.textContent = count;
                    badge.style.display = 'inline-flex';
                    if (btn) btn.style.boxShadow = '0 0 0 2px rgba(239,68,68,.5)';
                } else {
                    badge.style.display = 'none';
                    if (btn) btn.style.boxShadow = '';
                }
            },

            open() {
                const drawer = document.getElementById('admin-drawer');
                const overlay = document.getElementById('admin-drawer-overlay');
                if (drawer) drawer.style.right = '0';
                if (overlay) overlay.style.display = 'block';
                this._isOpen = true;
                this._render();
            },

            close() {
                const drawer = document.getElementById('admin-drawer');
                const overlay = document.getElementById('admin-drawer-overlay');
                if (drawer) drawer.style.right = '-400px';
                if (overlay) overlay.style.display = 'none';
                this._isOpen = false;
            },

            toggle() {
                if (this._isOpen) this.close(); else this.open();
            },

            _render() {
                const container = document.getElementById('admin-drawer-msgs');
                if (!container) return;
                if (this._msgs.length === 0) {
                    container.innerHTML = '<p style="text-align:center;color:var(--text-muted);font-family:Lato,sans-serif;font-size:13px;padding:40px 16px">Nenhuma mensagem ainda.</p>';
                    return;
                }
                // Pendentes primeiro, depois por hora
                const sorted = this._msgs.slice().sort(function (a, b) {
                    if (a.status === 'pending' && b.status !== 'pending') return -1;
                    if (a.status !== 'pending' && b.status === 'pending') return 1;
                    return 0;
                });
                const openReplies = new Set();
                container.querySelectorAll('.reply-row').forEach(function (el) {
                    const id = el.closest('[data-msg-id]');
                    if (id) openReplies.add(id.dataset.msgId);
                });
                container.innerHTML = sorted.map(function (m) {
                    return WebinarEngine.AdminInbox._cardHtml(m);
                }).join('');
                // Reabre inputs de resposta que estavam abertos
                openReplies.forEach(function (id) {
                    const card = container.querySelector('[data-msg-id="' + id + '"]');
                    if (card) WebinarEngine.AdminInbox._openReplyInput(card, id);
                });
            },

            _cardHtml(m) {
                const color = avatarColor(m.name || '?');
                const initial = (m.name || '?').charAt(0).toUpperCase();
                const statusMap = {
                    pending: '<span style="background:rgba(245,158,11,.15);color:#d97706;border:1px solid rgba(245,158,11,.3);border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;font-family:Montserrat,sans-serif">⏳ pendente</span>',
                    approved: '<span style="background:rgba(34,197,94,.1);color:#16a34a;border:1px solid rgba(34,197,94,.25);border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;font-family:Montserrat,sans-serif">✓ aprovado</span>',
                    rejected: '<span style="background:rgba(239,68,68,.1);color:#dc2626;border:1px solid rgba(239,68,68,.25);border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;font-family:Montserrat,sans-serif">✕ rejeitado</span>',
                };
                const replyHtml = m.admin_reply
                    ? '<div style="margin-top:6px;background:rgba(34,197,94,.07);border-left:2px solid #16a34a;border-radius:0 4px 4px 0;padding:5px 8px;font-family:Lato,sans-serif;font-size:12px;color:var(--text-secondary)"><strong style="color:#16a34a;font-size:11px">↩ Equipe:</strong> ' + escHtml(m.admin_reply) + '</div>'
                    : '';
                const approveBtn = m.status === 'pending'
                    ? '<button class="inbox-btn" data-action="approve" data-id="' + m.id + '" style="background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);color:#16a34a;border-radius:6px;padding:4px 10px;font-size:11px;font-family:Montserrat,sans-serif;font-weight:700;cursor:pointer">✓ Aprovar</button>'
                    : '';
                const rejectBtn = m.status === 'pending'
                    ? '<button class="inbox-btn" data-action="reject" data-id="' + m.id + '" style="background:rgba(239,68,68,.08);border:1px solid rgba(239,68,68,.2);color:#dc2626;border-radius:6px;padding:4px 10px;font-size:11px;font-family:Montserrat,sans-serif;font-weight:700;cursor:pointer">✕ Rejeitar</button>'
                    : '';
                const replyBtn = m.status !== 'rejected'
                    ? '<button class="inbox-btn" data-action="reply" data-id="' + m.id + '" style="background:rgba(59,130,246,.1);border:1px solid rgba(59,130,246,.25);color:#3b82f6;border-radius:6px;padding:4px 10px;font-size:11px;font-family:Montserrat,sans-serif;font-weight:700;cursor:pointer">↩ Responder</button>'
                    : '';
                const btns = (approveBtn || replyBtn || rejectBtn)
                    ? '<div style="display:flex;gap:5px;flex-wrap:wrap;margin-top:8px">' + approveBtn + replyBtn + rejectBtn + '</div>'
                    : '';
                return '<div data-msg-id="' + m.id + '" style="padding:12px;border-bottom:1px solid var(--border);' + (m.status === 'pending' ? 'background:rgba(245,158,11,.03)' : '') + '">' +
                    '<div style="display:flex;align-items:flex-start;gap:8px">' +
                        '<div style="width:28px;height:28px;border-radius:50%;background:' + color + ';display:flex;align-items:center;justify-content:center;font-family:Montserrat,sans-serif;font-size:11px;font-weight:700;color:#fff;flex-shrink:0">' + escHtml(initial) + '</div>' +
                        '<div style="flex:1;min-width:0">' +
                            '<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:3px">' +
                                '<span style="font-family:Montserrat,sans-serif;font-size:12px;font-weight:700;color:var(--text-primary)">' + escHtml(m.name) + '</span>' +
                                (m.ts ? '<span style="font-family:Lato,sans-serif;font-size:10px;color:var(--text-muted)">' + escHtml(m.ts) + '</span>' : '') +
                                (statusMap[m.status] || '') +
                            '</div>' +
                            '<p style="font-family:Lato,sans-serif;font-size:13px;color:var(--text-primary);margin:0;line-height:1.4;word-wrap:break-word">' + escHtml(m.message) + '</p>' +
                            replyHtml +
                            btns +
                        '</div>' +
                    '</div>' +
                '</div>';
            },

            _openReplyInput(card, msgId) {
                if (card.querySelector('.reply-row')) return;
                const row = document.createElement('div');
                row.className = 'reply-row';
                row.style.cssText = 'display:flex;gap:6px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border)';
                row.innerHTML =
                    '<input type="text" placeholder="Resposta privada..." style="flex:1;background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;padding:7px 10px;font-family:Lato,sans-serif;font-size:12px;color:var(--text-primary);outline:none;-webkit-appearance:none">' +
                    '<button style="background:var(--accent-gold);color:#fff;border:none;border-radius:6px;padding:7px 12px;font-family:Montserrat,sans-serif;font-weight:700;font-size:11px;cursor:pointer;white-space:nowrap">Enviar</button>';
                card.querySelector('div > div:last-child').appendChild(row);
                const input = row.querySelector('input');
                const sendBtn = row.querySelector('button');
                input.focus();
                const send = async function () {
                    const text = input.value.trim();
                    if (!text) return;
                    sendBtn.disabled = true;
                    try {
                        await fetch('/admin/api/chat-reply/' + msgId, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ reply: text })
                        });
                        await WebinarEngine.AdminInbox.poll();
                    } catch (e) { sendBtn.disabled = false; }
                };
                sendBtn.onclick = send;
                input.addEventListener('keydown', function (e) { if (e.key === 'Enter') send(); });
            },

            async _action(action, msgId) {
                if (action === 'reply') {
                    const card = document.querySelector('[data-msg-id="' + msgId + '"]');
                    if (!card) return;
                    if (card.querySelector('.reply-row')) {
                        card.querySelector('.reply-row').remove();
                    } else {
                        this._openReplyInput(card, msgId);
                    }
                    return;
                }
                try {
                    if (action === 'approve') {
                        await fetch('/admin/api/moderate-chat/' + msgId, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ action: 'approve' })
                        });
                    } else if (action === 'reject') {
                        await fetch('/admin/api/moderate-chat/' + msgId, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ action: 'reject' })
                        });
                    }
                    await this.poll();
                } catch (e) {}
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
        ['chat', 'offer'].forEach(function (t) {
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

    // ── Admin: toggle inbox drawer ────────────────────────────────────────────
    window.toggleAdminInbox = function () {
        WebinarEngine.AdminInbox.toggle();
    };
    window.closeAdminInbox = function () {
        WebinarEngine.AdminInbox.close();
    };

    // ── Reações ───────────────────────────────────────────────────────────────
    window.sendReaction = function (emoji) {
        WebinarEngine.Reactions.send(emoji);
    };

    // ── Enquete (admin) ───────────────────────────────────────────────────────
    window.togglePollModal = function () {
        const modal = document.getElementById('poll-modal');
        if (!modal) return;
        const isOpen = modal.style.display === 'flex';
        modal.style.display = isOpen ? 'none' : 'flex';
        if (!isOpen) {
            document.getElementById('poll-question').focus();
        }
    };
    window.closePollModal = function () {
        const modal = document.getElementById('poll-modal');
        if (modal) modal.style.display = 'none';
    };
    window.launchPoll = async function () {
        const question = (document.getElementById('poll-question').value || '').trim();
        const options = Array.from(document.querySelectorAll('.poll-opt-input'))
            .map(function (i) { return i.value.trim(); })
            .filter(function (v) { return v; });
        if (!question) { alert('Digite a pergunta.'); return; }
        if (options.length < 2) { alert('Adicione pelo menos 2 opções.'); return; }
        try {
            const r = await fetch('/admin/api/webinar/' + window.WEBINAR_ID + '/poll', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: question, options: options })
            });
            if (!r.ok) throw new Error('HTTP ' + r.status);
            closePollModal();
            document.getElementById('poll-question').value = '';
            document.querySelectorAll('.poll-opt-input').forEach(function (i) { i.value = ''; });
            WebinarEngine.Poll.fetch();
        } catch (err) {
            alert('Erro ao lançar enquete: ' + err.message);
        }
    };

    // Fechar modal com ESC
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('poll-modal');
            if (modal && modal.style.display === 'flex') closePollModal();
        }
    });

    // Admin: ações no drawer (aprovar/rejeitar/responder)
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('.inbox-btn');
        if (!btn) return;
        e.preventDefault();
        WebinarEngine.AdminInbox._action(btn.dataset.action, btn.dataset.id);
    });

    // ── Admin: enviar mensagem no chat como "Equipe" ──────────────────────────
    window.adminSendChat = async function () {
        const input = document.getElementById('admin-chat-input');
        if (!input) return;
        const msg = input.value.trim();
        if (!msg) return;
        input.value = '';
        input.disabled = true;
        try {
            const resp = await fetch('/admin/api/webinar/' + window.WEBINAR_ID + '/admin-chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: msg })
            });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            const data = await resp.json();
            const newId = data.id || null;
            WebinarEngine.Chat.addMessage('Equipe', msg, false, null, null, newId);
            // Evita duplicação: PublicChat.poll não vai buscar essa msg no próximo tick
            if (newId && newId > WebinarEngine.PublicChat.lastId) {
                WebinarEngine.PublicChat.lastId = newId;
            }
        } catch (err) {
            alert('Erro ao enviar: ' + err.message);
            input.value = msg;
        } finally {
            input.disabled = false;
            input.focus();
        }
    };

    // ── Admin: fixar mensagem personalizada ──────────────────────────────────
    window.adminPinPrompt = function () {
        const msg = prompt('Mensagem para fixar no topo do chat:');
        if (!msg || !msg.trim()) return;
        fetch('/admin/api/create-pinned/' + window.WEBINAR_ID, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg.trim() })
        }).catch(function () {});
    };

    // Admin: desafixar mensagem pelo banner
    window.adminUnpin = function (chatId) {
        fetch('/admin/api/pin-chat/' + chatId, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pin: false })
        }).catch(function () {});
        const el = document.getElementById('chat-pinned-banner');
        if (el) el.remove();
        if (WebinarEngine.PublicChat) WebinarEngine.PublicChat.pinnedId = null;
    };

    // Admin: ações em mensagens do admin no chat (pin/unpin/edit/delete)
    document.addEventListener('click', async function (e) {
        const btn = e.target.closest('.admin-chat-btn');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const chatId = btn.dataset.chatId;
        const action = btn.dataset.action;
        if (!chatId) return;

        if (action === 'delete') {
            if (!confirm('Apagar esta mensagem do chat?')) return;
            btn.disabled = true;
            try {
                const r = await fetch('/admin/api/chat/' + chatId, { method: 'DELETE' });
                if (!r.ok) throw new Error('HTTP ' + r.status);
                const msgEl = btn.closest('.chat-msg');
                if (msgEl) {
                    msgEl.style.transition = 'opacity .25s';
                    msgEl.style.opacity = '0';
                    setTimeout(function () { msgEl.remove(); }, 250);
                }
            } catch (err) {
                btn.disabled = false;
                alert('Erro ao apagar: ' + err.message);
            }
        } else if (action === 'edit') {
            const msgEl = btn.closest('.chat-msg');
            const pEl = msgEl ? msgEl.querySelector('p') : null;
            if (!pEl) return;
            const newText = prompt('Editar mensagem:', pEl.textContent);
            if (!newText || !newText.trim()) return;
            try {
                const r = await fetch('/admin/api/chat/' + chatId, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: newText.trim() })
                });
                if (!r.ok) throw new Error('HTTP ' + r.status);
                pEl.textContent = newText.trim();
            } catch (err) {
                alert('Erro ao editar: ' + err.message);
            }
        } else if (action === 'pin') {
            try {
                await fetch('/admin/api/pin-chat/' + chatId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pin: true })
                });
            } catch (err) {
                alert('Erro ao fixar: ' + err.message);
            }
        } else if (action === 'unpin') {
            try {
                await fetch('/admin/api/pin-chat/' + chatId, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ pin: false })
                });
                const el = document.getElementById('chat-pinned-banner');
                if (el) el.remove();
                if (WebinarEngine.PublicChat) WebinarEngine.PublicChat.pinnedId = null;
            } catch (err) {
                alert('Erro ao desafixar: ' + err.message);
            }
        }
    });

    // Admin: deletar comentario da timeline direto na sala
    document.addEventListener('click', async function (e) {
        const btn = e.target.closest('.chat-delete-btn');
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const eventId = btn.dataset.eventId;
        if (!eventId) return;
        if (!confirm('Excluir este comentário da timeline? Ação definitiva.')) return;
        btn.disabled = true;
        btn.textContent = '…';
        try {
            const resp = await fetch('/admin/api/timeline-event/' + eventId, { method: 'DELETE' });
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            // Remove do DOM com fade
            const msg = btn.closest('.chat-msg');
            if (msg) {
                msg.style.transition = 'opacity .25s, transform .25s';
                msg.style.opacity = '0';
                msg.style.transform = 'translateX(8px)';
                setTimeout(function () { msg.remove(); }, 250);
            }
            // Tambem remove de WebinarEngine.events pra nao redisparar em seek
            WebinarEngine.events = WebinarEngine.events.filter(function (ev) { return ev.id != eventId; });
            WebinarEngine.firedEvents.add(parseInt(eventId));
        } catch (err) {
            btn.disabled = false;
            btn.textContent = '🗑';
            alert('Erro ao excluir: ' + err.message + '. Você está logado como admin?');
        }
    });

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
