# Protocolo de teste de carga — AutoWebinar

Simula participantes reais no lançamento (registrar → sala → heartbeat → chat).

## Pré-requisitos

```bash
brew install k6
```

Ou veja https://k6.io/docs/get-started/installation/

## Preparação

1. **Ambiente**: rode o teste contra **staging** ou um banco de teste — o script cria registrantes de verdade.
2. **Slug**: cadastre um webinário no admin e passe o slug pela variável de ambiente.
3. **Data do webinário**: ajuste `test_date` para agora −20min, assim a sala fica aberta.
4. **DB**: SQLite **não aguenta** >50 conexões simultâneas com escrita. Rode com **Postgres** antes do teste real (veja `MIGRATION.md`).

## Execução

```bash
# Teste rápido (20 VUs, 1min) — smoke test
BASE_URL=https://seu-dominio.com SLUG=meu-webinar SCENARIO=quick k6 run tests/loadtest.js

# Teste completo (até 500 VUs, ~8min) — protocolo oficial
BASE_URL=https://seu-dominio.com SLUG=meu-webinar k6 run tests/loadtest.js

# Teste de pico (500 VUs em 10s) — simula abertura de sala
BASE_URL=https://seu-dominio.com SLUG=meu-webinar SCENARIO=spike k6 run tests/loadtest.js
```

## Critérios de aprovação

| Métrica                        | Limite     |
|--------------------------------|------------|
| http_req_duration (p95)        | < 800ms    |
| http_req_failed (rate)         | < 1%       |
| heartbeat (p95)                | < 300ms    |
| user-chat POST (p95)           | < 500ms    |

Se algum threshold falhar, o k6 encerra com exit-code ≠ 0 (útil em CI).

## O que monitorar em paralelo

Enquanto o k6 roda, observe no servidor:

- **CPU** (`top`, `htop`)
- **Memória** (`free -m`, container memory)
- **Conexões abertas** (`ss -tn state established | wc -l`)
- **Logs do Flask** (erros 500, timeouts)
- **Banco**: locks / slow queries

## Roteiro do lançamento (sugestão)

1. **D−3**: smoke test com 20 VUs em staging → corrige erros.
2. **D−1**: full test (500 VUs) em staging espelho de prod.
3. **D−1h**: spike test em prod com monitoramento redobrado.
4. **D0**: desligue o k6 30min antes do início real.

## Limpeza pós-teste

Os registrantes criados têm telefones `(XX) 9XXXXXXXX` inventados. Para limpar:

```sql
DELETE FROM live_presence
  WHERE registrant_id IN (SELECT id FROM registrants WHERE webinar_id = <ID>);
DELETE FROM user_chat_messages WHERE webinar_id = <ID>;
DELETE FROM registrants WHERE webinar_id = <ID> AND hotmart_transaction IS NULL;
```
