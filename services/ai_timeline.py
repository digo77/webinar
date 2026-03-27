"""
Gerador de timeline com IA.
- Transcreve áudio via OpenAI Whisper (com timestamps)
- Sugere mensagens de chat via Claude (Anthropic)
"""
import os
import json


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

    client = anthropic_sdk.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY', ''))

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
