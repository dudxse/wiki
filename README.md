# Wikipedia Summarizer API

API para extração e sumarização de artigos da Wikipedia com cache em Postgres.  
Arquitetura organizada em camadas (API/serviços/repositórios), com foco em confiabilidade e operação em ambiente corporativo.

---

## Escopo do desafio

- Endpoint para criar resumo com `url` e `word_count`, com cache por URL + contagem de palavras.
- Endpoint para consulta de resumos existentes por URL.
- Scraping com limpeza de conteúdo da Wikipedia.
- Sumarização via LLM com fallback de modelo.
- Persistência em Postgres + migrações Alembic.
- Containerização com Docker Compose.
- Testes automatizados com pytest.

---

## Início rápido

Você pode rodar a aplicação completa (API + Banco de Dados + Redis) com Docker Compose.

### Pré-requisitos

- Docker Desktop e Docker Compose instalados.
- Uma chave de API da OpenAI (`OPENAI_API_KEY`).

### Passos

1. **Configure o ambiente**
   Crie um arquivo `.env` na raiz do projeto (copie de `.env.example`) e adicione sua chave:

   ```bash
   cp .env.example .env
   # Edite o arquivo e defina OPENAI_API_KEY=sk-...
   ```

2. **Inicie os serviços**

   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env up --build -d
   ```

   A API estará disponível em `http://localhost:8080`.

3. **Acesse a Documentação**
   - Swagger UI: [http://localhost:8080/docs](http://localhost:8080/docs)
   - ReDoc: [http://localhost:8080/redoc](http://localhost:8080/redoc)

---

## Como testar a API (rápido)

### Windows PowerShell
```powershell
$url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
$encoded = [uri]::EscapeDataString($url)

# Health
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/health/live"
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/health/ready"

# Criar resumo
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/summaries" `
  -ContentType "application/json" `
  -Body (@{ url = $url; word_count = 80 } | ConvertTo-Json)

# Buscar resumo (mais recente)
Invoke-RestMethod -Method Get -Uri "http://localhost:8080/summaries?url=$encoded"
```

### curl (Linux/macOS ou curl.exe no Windows)
```bash
# Health
curl -s http://localhost:8080/health/live
curl -s http://localhost:8080/health/ready

# Criar resumo
curl -s -X POST http://localhost:8080/summaries \
  -H "Content-Type: application/json" \
  -d '{"url":"https://en.wikipedia.org/wiki/Artificial_intelligence","word_count":80}'

# Buscar resumo (mais recente)
curl -s -G "http://localhost:8080/summaries" \
  --data-urlencode "url=https://en.wikipedia.org/wiki/Artificial_intelligence"
```

---

## Fluxo de uso e respostas esperadas

- `GET /summaries` só busca no cache. Se a URL ainda não foi processada, retorna **404**.
- Para gerar e salvar o resumo, use `POST /summaries` primeiro.
- `word_count` no `GET` filtra pelo tamanho exato. Se você omitir, o endpoint retorna o resumo mais recente.
- O campo `source` indica se veio do cache (`cache`) ou foi gerado agora (`generated`).

### Exemplo (PowerShell): gerar e depois buscar
```powershell
$url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
$encoded = [uri]::EscapeDataString($url)

Invoke-RestMethod -Method Post -Uri "http://localhost:8080/summaries" `
  -ContentType "application/json" `
  -Body (@{ url = $url; word_count = 80 } | ConvertTo-Json)

Invoke-RestMethod -Method Get -Uri "http://localhost:8080/summaries?url=$encoded&word_count=80"
```

---

## Tradução (Português) e status `skipped`

O campo `summary_pt_origin` pode aparecer como `skipped`. Isso acontece quando o texto já parece estar em português
e a tradução é pulada automaticamente (heurística para evitar retradução). Nesse caso, `summary_pt` retorna o próprio
texto de `summary` e o status indica que a tradução foi dispensada.

Valores possíveis de `summary_pt_origin`:
- `llm`: tradução feita pelo modelo principal.
- `llm_fallback`: tradução feita pelo modelo de fallback.
- `skipped`: texto já parecia estar em português.
- `disabled`: tradução desabilitada por configuração.
- `unavailable`: chave inválida/ausente, tradução não disponível.
- `error`: tentativa de tradução falhou.

---

## Problemas comuns

### Saída com caracteres quebrados no PowerShell
Se você ver caracteres estranhos (ex.: `Ã©`, `Ãª`), ajuste a codificação do terminal:

```powershell
chcp 65001
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

Depois disso, rode novamente o `Invoke-RestMethod`.

---

## Segurança e Robustez

Medidas aplicadas no projeto:

1. **Least Privilege**
   - Container não roda como root (usuário dedicado `appuser`).
2. **Supply Chain**
   - Build determinístico usando `requirements.lock` para garantir versões consistentes.
3. **Observabilidade**
   - Logs em JSON (`JSONFormatter`) para integração com ferramentas de monitoramento.
   - Logs do LLM incluem modelo, tentativa e hash do prompt para auditoria de versões.
4. **Resiliência**
   - Migrações automáticas via `entrypoint.sh`.
   - Rate limiting com Redis + SlowAPI.
   - Validação estrita de URL (apenas `wikipedia.org`) para reduzir risco de SSRF.
   - Retentativas com backoff em chamadas ao LLM.

---

## Funcionalidades

- Scraping limpo: remove elementos não textuais (ex.: tabelas e referências).
- Sumarização com LLM: LangChain + OpenAI com fallback automático para modelo secundário.
- Textos longos usam estratégia map-reduce por chunks para evitar limites de tokens.
- Cache: persistência por URL + `word_count` para reduzir custo e latência.
- Tradução opcional: PT-BR quando habilitado.
- Tradução best-effort: se falhar, `summary_pt` fica `null` e `summary_pt_origin=error`.
- Saída estruturada do LLM em JSON para reduzir variação e facilitar parsing.
- Normalização de URL: URLs são normalizadas e forçadas para `https` para evitar duplicidade de cache.
- Containerização: Docker + Docker Compose.

---

## Referência da API

### Criar Resumo
Gera um novo resumo ou retorna um existente do cache.

`POST /summaries`

**Body:**
```json
{
  "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
  "word_count": 200
}
```

### Consultar Resumo
Busca um resumo já processado.

`GET /summaries`

**Query Params:**
- `url`: URL do artigo da Wikipedia.
- `word_count` (opcional): Filtra por tamanho específico. Se omitido, retorna o mais recente.

---

## Decisões e trade-offs

- **Cache por `url` + `word_count`**: evita recomputação e reduz custo. Trade-off: múltiplas variações de tamanho geram múltiplos registros.
- **Fallback de modelo**: se o modelo principal falha, tenta o secundário antes do extrativo simples. Trade-off: latência maior em cenários de falha.
- **Validação estrita de Wikipedia**: reduz risco de SSRF e conteúdo indesejado. Trade-off: bloqueia URLs válidas fora de `wikipedia.org`.

---

## Exemplos de Resposta

**POST /summaries** (gerado com fallback de modelo):
```json
{
  "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
  "word_count": 200,
  "actual_word_count": 187,
  "summary": "Artificial intelligence (AI) is a field of computing focused on building systems that perform tasks requiring human-like intelligence...",
  "summary_origin": "llm_fallback",
  "summary_pt": "Inteligência artificial (IA) é um campo da computação focado em construir sistemas que realizam tarefas associadas à inteligência humana...",
  "summary_pt_origin": "llm_fallback",
  "source": "generated",
  "created_at": "2026-01-27T12:00:00Z"
}
```

**GET /summaries** (cache):
```json
{
  "url": "https://en.wikipedia.org/wiki/Artificial_intelligence",
  "word_count": 200,
  "actual_word_count": 187,
  "summary": "Artificial intelligence (AI) is a field of computing focused on building systems that perform tasks requiring human-like intelligence...",
  "summary_origin": "llm_fallback",
  "summary_pt": "Inteligência artificial (IA) é um campo da computação focado em construir sistemas que realizam tarefas associadas à inteligência humana...",
  "summary_pt_origin": "llm_fallback",
  "source": "cache",
  "created_at": "2026-01-27T12:00:00Z"
}
```

---

## Exemplos de Erro

**400 Bad Request** (URL fora de `wikipedia.org`):
```json
{
  "detail": "URL must belong to wikipedia.org."
}
```

**422 Unprocessable Entity** (`word_count` acima do limite):
```json
{
  "detail": "word_count must be <= 500."
}
```
Exemplo quando `SUMMARY_WORD_COUNT_MAX=500`.

**404 Not Found** (resumo não encontrado no cache):
```json
{
  "detail": "Summary not found for the provided URL."
}
```

**502 Bad Gateway** (falha em serviço externo):
```json
{
  "detail": "Wikipedia scraping failed: Failed to fetch Wikipedia content."
}
```

---

## Configuração

As configurações são gerenciadas via variáveis de ambiente (arquivo `.env`).

### Sobre o `.env` no envio do desafio

- **Não** versionar o arquivo `.env` com credenciais reais.
- Versione apenas o `.env.example` com placeholders.
- O avaliador deve copiar `.env.example` para `.env` e preencher as chaves localmente.

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `POSTGRES_USER` | Usuário do Postgres (compose). | postgres |
| `POSTGRES_PASSWORD` | Senha do Postgres (compose). | postgres |
| `POSTGRES_DB` | Nome do banco. | summaries |
| `POSTGRES_HOST` | Host do Postgres (compose). | db |
| `POSTGRES_PORT` | Porta do Postgres. | 5432 |
| `DATABASE_URL` | URL completa do PostgreSQL (se definida, sobrescreve os campos acima). | (Auto no Docker) |
| `API_PORT` | Porta publicada da API no host (compose). | 8080 |
| `TZ` | Timezone dos containers. | UTC |
| `REDIS_PASSWORD` | Senha do Redis usado no rate limit. | change-me |
| `OPENAI_API_KEY` | **Obrigatório**. Chave da API da OpenAI. | - |
| `OPENAI_MODEL` | **Obrigatório**. Modelo principal. | - |
| `OPENAI_FALLBACK_MODEL` | Modelo secundário usado se o principal falhar. | (Opcional) |
| `LOG_LEVEL` | **Obrigatório**. Nível de log (INFO, DEBUG, etc). | - |
| `HTTP_TIMEOUT_SECONDS` | Timeout para requests HTTP da Wikipedia (segundos). | 10 |
| `LLM_TIMEOUT_SECONDS` | Timeout para chamadas ao LLM (segundos). | 30 |
| `LLM_MAX_RETRIES` | Quantidade de retentativas para chamadas ao LLM. | 2 |
| `LLM_RETRY_BACKOFF_SECONDS` | Backoff base (segundos) entre retentativas do LLM. | 1.0 |
| `WIKIPEDIA_USER_AGENT` | **Obrigatório**. User-Agent para requests ao Wikipedia. | - |
| `WIKIPEDIA_MIN_ARTICLE_WORDS` | Mínimo de palavras extraídas para permitir resumo. | 50 |
| `WIKIPEDIA_MAX_CONTENT_BYTES` | Máximo de bytes permitidos no download do artigo. | 2000000 |
| `WIKIPEDIA_MAX_REDIRECTS` | Máximo de redirects permitidos. | 5 |
| `SUMMARY_WORD_COUNT_MAX` | Valor máximo aceito em `word_count`. | 500 |
| `ENABLE_PORTUGUESE_TRANSLATION` | Habilita tradução automática para PT-BR. | True |
| `RATE_LIMIT_ENABLED` | Habilita rate limiting na API. | True |
| `RATE_LIMIT_REDIS_URL` | URL do Redis usada pelo rate limiter. | redis://redis:6379/0 |
| `RATE_LIMIT_TRUST_PROXY_HEADERS` | Considera headers de proxy para IP do cliente. | False |
| `RATE_LIMIT_DEFAULT` | Rate limit global padrão. | 120/minute |
| `RATE_LIMIT_POST_SUMMARIES` | Rate limit do POST /summaries. | 30/minute |
| `RATE_LIMIT_GET_SUMMARIES` | Rate limit do GET /summaries. | 300/minute |

Se o modelo principal falhar e `OPENAI_FALLBACK_MODEL` não estiver definido, a API usa um resumo extrativo simples.
Obs: no Docker Compose, `RATE_LIMIT_REDIS_URL` é sobrescrito para `redis://:${REDIS_PASSWORD}@redis:6379/0`.

---

## Operação

**Healthcheck**
- API:
  - `GET /health/live` (liveness simples)
  - `GET /health/ready` (readiness com DB + Redis quando habilitado)
- Infra: Postgres, Redis e API já têm healthcheck no `docker-compose.yml`.

**Métricas esperadas (sugestões)**
- Latência p50/p95 por endpoint (`/summaries` POST/GET).
- Taxa de acerto de cache (cache hit rate).
- Erros por upstream (Wikipedia/OpenAI) e por tipo (400/404/502).
- Tempo de scraping e tempo de LLM.
- Consumo de tokens e custo estimado por resumo (se disponível via observabilidade).

**Rate limit**
- Se o Redis estiver indisponível, o rate limit cai automaticamente para armazenamento em memória.

---

## Stack Tecnológica

| Componente | Tecnologia |
|------------|------------|
| **Framework Web** | FastAPI |
| **Banco de Dados** | PostgreSQL (via SQLAlchemy 2.0 + psycopg) |
| **Migrações** | Alembic |
| **LLM & Orquestração** | LangChain + OpenAI |
| **Scraping** | BeautifulSoup4 + HTTPX |
| **Infraestrutura** | Docker + Redis |

---

## Desenvolvimento

Para rodar os testes localmente:

```bash
# Instale as dependências (ambiente virtual recomendado)
# Para paridade com o Docker, prefira o lockfile.
pip install -r requirements.lock
# Alternativa para desenvolvimento rápido:
# pip install -r requirements.txt

# Execute os testes
pytest
```

## Comandos rápidos (Makefile)

```bash
make dev-install
make test
make lint
make typecheck
make up
make itest
```

## Testes de integração (opcional)

1. Suba os serviços:
   ```bash
   docker compose -f infra/docker-compose.yml --env-file .env up --build -d
   ```
2. Rode os testes:
   ```bash
   RUN_INTEGRATION_TESTS=1 pytest -m integration
   ```
   Para testar o endpoint de resumo:
   ```bash
   RUN_INTEGRATION_TESTS=1 RUN_SUMMARIES_INTEGRATION=1 pytest -m integration
   ```

## Arquitetura e trade-offs

Veja `docs/DECISIONS.md` para as decisões arquiteturais e trade-offs principais.

## CI

O pipeline do GitHub Actions roda `pytest` em `push` e `pull_request`.
