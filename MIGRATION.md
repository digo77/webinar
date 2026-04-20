# Migração SQLite → Postgres (produção)

SQLite é OK pra desenvolvimento e webinars com até ~30 participantes.
Para lançamentos sérios (100+ simultâneos), **migre pra Postgres**.

## Por quê

SQLite usa lock de banco inteiro em escrita. Com heartbeats a cada 15s e chat ao vivo:
- 200 users → ~13 escritas/s → OK
- 500 users → ~33 escritas/s → **lock starvation**
- 1000+ users → requisições começam a falhar em segundos

Postgres lida com milhares de conexões simultâneas sem lock global.

## Passo a passo

### 1. Provisionar Postgres

**Opção A — Railway / Render / Fly**:
```bash
railway add -d postgres
# ou: render dashboard → New Postgres
```

**Opção B — Docker local** (staging):
```bash
docker run -d --name autowebinar-pg \
  -e POSTGRES_PASSWORD=senha \
  -e POSTGRES_DB=autowebinar \
  -p 5432:5432 \
  postgres:16
```

### 2. Instalar driver

Adicione a `requirements.txt`:
```
psycopg2-binary==2.9.9
```

### 3. Configurar env var

```bash
export DATABASE_URL="postgresql://user:senha@host:5432/autowebinar"
```

A config já lê `DATABASE_URL` automaticamente (veja [config.py:6](config.py:6)).

### 4. Migrar dados (se já tiver produção em SQLite)

```bash
pip install pgloader
pgloader sqlite:///instance/autowebinar.db postgresql://user:senha@host/autowebinar
```

Ou manual via CSV:
```bash
sqlite3 instance/autowebinar.db ".headers on" ".mode csv" ".output registrants.csv" "SELECT * FROM registrants;"
# depois: \copy registrants FROM 'registrants.csv' WITH CSV HEADER; no psql
```

### 5. Primeira boot

Na primeira execução com `DATABASE_URL` apontando para Postgres, `db.create_all()`
em [app.py:79](app.py:79) cria todas as tabelas. O `migrate_db()` (idempotente)
adiciona colunas que vierem a ser novas.

### 6. Limpeza de presença (job periódico)

Rodando em prod, adicione um cron pra limpar `live_presence` antigos:

```sql
DELETE FROM live_presence WHERE last_seen < NOW() - INTERVAL '10 minutes';
```

Crie um job a cada 5min (cron do deploy ou `pg_cron`).

## Ajustes de performance opcionais

- **Pool de conexões**: SQLAlchemy já usa pool; em Postgres, defina
  `SQLALCHEMY_ENGINE_OPTIONS = {"pool_size": 20, "max_overflow": 40}`.
- **Redis para presença**: se superar 1000 users simultâneos, troque `live_presence`
  por Redis com TTL de 45s. Economiza centenas de writes/s no DB.
- **Gunicorn workers**: rode com `gunicorn -w 4 -k gevent --worker-connections 1000 app:app`.
