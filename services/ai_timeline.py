"""
Gerador de timeline com IA.
- Transcreve áudio via OpenAI Whisper (com timestamps)
- Parseia transcrição colada em texto com timestamps
- Sugere mensagens de chat via Claude (Anthropic)
"""
import os
import re
import json


def parse_transcript_text(text: str) -> list:
    """
    Parseia texto de transcrição colado pelo usuário.
    Suporta múltiplos formatos:
      - [0:45] texto          (bracket mm:ss)
      - [1:23:45] texto       (bracket hh:mm:ss)
      - 0:45 texto            (sem bracket)
      - 00:00:45,000 --> ...  (SRT/VTT — usa o tempo de início)
      - (45s) texto           (segundos com s)
      - 45: texto             (segundos puro)
    Retorna: [{'second': int, 'text': str}, ...]
    """
    segments = []
    lines = text.strip().splitlines()

    # Regex para cada formato
    patterns = [
        # SRT/VTT: 00:01:23,456 --> 00:01:30,000  ou  00:01:23.456 --> ...
        (re.compile(r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d+)\s*-->'), 'srt'),
        # [hh:mm:ss] ou [mm:ss]
        (re.compile(r'^\[(\d{1,2}):(\d{2})(?::(\d{2}))?\]\s*(.*)'), 'bracket'),
        # mm:ss texto (sem bracket, no início da linha)
        (re.compile(r'^(\d{1,2}):(\d{2})(?::(\d{2}))?\s+(.+)'), 'plain'),
        # (45s) texto
        (re.compile(r'^\((\d+)s\)\s*(.*)'), 'sec_paren'),
        # 45: texto
        (re.compile(r'^(\d+):\s+(.+)'), 'sec_colon'),
    ]

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        matched = False

        # SRT: linha de timestamps, texto vem na próxima linha
        m = patterns[0][0].match(line)
        if m:
            h, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3))
            second = h * 3600 + mm * 60 + ss
            # Próxima linha(s) são o texto
            text_parts = []
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r'^\d+$', lines[i].strip()):
                next_line = lines[i].strip()
                if re.match(r'\d{1,2}:\d{2}:\d{2}[,.]', next_line):
                    break
                text_parts.append(next_line)
                i += 1
            if text_parts:
                segments.append({'second': second, 'text': ' '.join(text_parts)})
            continue

        # [mm:ss] ou [hh:mm:ss]
        m = patterns[1][0].match(line)
        if m:
            p1, p2, p3, txt = m.group(1), m.group(2), m.group(3), m.group(4)
            if p3 is not None:
                second = int(p1) * 3600 + int(p2) * 60 + int(p3)
            else:
                second = int(p1) * 60 + int(p2)
            if txt.strip():
                segments.append({'second': second, 'text': txt.strip()})
            matched = True

        if not matched:
            # mm:ss texto
            m = patterns[2][0].match(line)
            if m:
                p1, p2, p3, txt = m.group(1), m.group(2), m.group(3), m.group(4)
                if p3 is not None:
                    second = int(p1) * 3600 + int(p2) * 60 + int(p3)
                else:
                    second = int(p1) * 60 + int(p2)
                segments.append({'second': second, 'text': txt.strip()})
                matched = True

        if not matched:
            # (45s) texto
            m = patterns[3][0].match(line)
            if m:
                segments.append({'second': int(m.group(1)), 'text': m.group(2).strip()})
                matched = True

        if not matched:
            # 45: texto
            m = patterns[4][0].match(line)
            if m:
                segments.append({'second': int(m.group(1)), 'text': m.group(2).strip()})

        i += 1

    # Ordena por segundo e remove duplicatas de segundo vazio
    segments = [s for s in segments if s['text']]
    segments.sort(key=lambda x: x['second'])
    return segments


def transcribe_audio(file_path: str) -> list:
    """
    Transcreve áudio via OpenAI Whisper API com timestamps de segmentos.
    Retorna: [{'second': int, 'text': str}, ...]
    """
    from openai import OpenAI

    client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY', ''))

    with open(file_path, 'rb') as f:
        response = client.audio.transcriptions.create(
            model='whisper-1',
            file=f,
            response_format='verbose_json',
            timestamp_granularities=['segment'],
        )

    segments = []
    raw_segs = getattr(response, 'segments', None) or []
    for seg in raw_segs:
        start = getattr(seg, 'start', None)
        text = getattr(seg, 'text', '') or ''
        if start is not None:
            segments.append({
                'second': int(float(start)),
                'text': text.strip(),
            })

    return segments


def suggest_chat_events(transcript_segments: list, product_context: str) -> list:
    """
    Usa Claude para sugerir mensagens de chat baseadas na transcrição.
    Retorna lista de dicts: [{trigger_second, author, message, reason}, ...]
    """
    import anthropic as anthropic_sdk

    api_key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not api_key:
        raise ValueError(
            'ANTHROPIC_API_KEY não configurada. '
            'Adicione a variável de ambiente no EasyPanel (serviço → Environment Variables).'
        )
    client = anthropic_sdk.Anthropic(api_key=api_key)

    # Monta transcrição com timestamps
    if transcript_segments:
        transcript_text = '\n'.join(
            f"[{seg['second']}s] {seg['text']}"
            for seg in transcript_segments
        )
    else:
        transcript_text = '(transcrição não disponível)'

    user_message = f"""Contexto do produto/webinário:
{product_context}

Transcrição com timestamps (em segundos):
{transcript_text}

Sugira entre 10 e 20 mensagens de chat simulado para engajamento e conversão.
Distribua estrategicamente ao longo do vídeo, concentrando mais nas viradas
de conteúdo (apresentação do produto, prova social, oferta, urgência).
Use nomes brasileiros variados e mensagens naturais, com emojis ocasionais.
Retorne APENAS JSON válido, sem nenhuma explicação ou markdown ao redor."""

    response = client.messages.create(
        model='claude-sonnet-4-5',
        max_tokens=4096,
        system="""Você é um especialista em webinários de vendas. Analise a transcrição \
deste webinário e sugira mensagens de chat simulado para aumentar o \
engajamento e conversão. As mensagens devem parecer naturais, de \
participantes reais assistindo ao vídeo ao vivo. Retorne APENAS JSON válido.

Formato de retorno (array JSON):
[
  {
    "trigger_second": 45,
    "author": "Mariana Silva",
    "message": "Que receita incrível! Já quero fazer isso em casa 😍",
    "reason": "Momento em que o Chef apresenta o produto pela primeira vez"
  }
]""",
        messages=[{'role': 'user', 'content': user_message}],
    )

    raw = response.content[0].text.strip()

    # Remove markdown code fences se presentes
    if raw.startswith('```'):
        lines = raw.split('\n')
        # Remove primeira e última linha (``` e ```)
        inner = lines[1:]
        if inner and inner[-1].strip().startswith('```'):
            inner = inner[:-1]
        raw = '\n'.join(inner).strip()

    return json.loads(raw)
