# Decisões de arquitetura e trade-offs

Este documento resume as principais decisões tomadas neste desafio e os trade-offs
aceitos para manter a solução robusta, clara e pronta para produção em uma API pequena.

## Escopo e camadas
- Decisão: manter uma separação clara entre API, serviços e repositórios.
- Por quê: melhora a testabilidade e torna o fluxo de negócio explícito sem o overhead de DDD pesado.
- Trade-off: não há um modelo de domínio completo nem agregados; o foco é velocidade de entrega e clareza.

## Estratégia de cache
- Decisão: cache por URL normalizada + `word_count`.
- Por quê: evita recomputação e custo em requisições repetidas e em diferentes tamanhos de resumo.
- Trade-off: múltiplos registros por artigo para tamanhos diferentes.

## Normalização e validação de URL
- Decisão: aceitar apenas `wikipedia.org`, normalizar caminhos e forçar `https` para reduzir duplicidades.
- Por quê: evita riscos de SSRF e reduz fragmentação do cache.
- Trade-off: rejeita algumas URLs válidas porém incomuns da Wikipedia.

## Seleção do "resumo mais recente"
- Decisão: selecionar o resumo mais recente por `id` em ordem decrescente.
- Por quê: evita depender do relógio do sistema; o `id` reflete a ordem de inserção de forma confiável.
- Trade-off: se registros forem inseridos fora de ordem, o `id` pode não refletir o tempo real.

## Resiliência e fallbacks
- Decisão: sumarizar com LLM e usar fallback extrativo quando o LLM falha.
- Por quê: mantém a API usável em falhas do LLM ou chaves inválidas.
- Trade-off: a qualidade do fallback é menor do que a do LLM.

## Comportamento de tradução
- Decisão: tradução para português é best-effort e não falha a requisição.
- Por quê: a tradução é opcional; o resumo principal ainda deve ser retornado.
- Trade-off: `summary_pt` pode ser `null` se a tradução falhar.

## Observabilidade e rate limiting
- Decisão: logs estruturados em JSON com request ID; rate limit opcional via Redis.
- Por quê: melhora depuração e prontidão para produção.
- Trade-off: Redis é necessário para o rate limit completo; testes desabilitam essa dependência.
