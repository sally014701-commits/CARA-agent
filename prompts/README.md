# Runtime Prompts

This folder documents only prompts that are sent to LLM providers during actual service runtime paths.

## Included

- `runtime_prompts/conversation_agent.md`
  - Runtime path: `POST /api/chat`
  - Provider/client: Anthropic
  - Model in code: `claude-sonnet-4-5`
  - Role: Customer-facing conversation confirmation and handoff to recommendation flow.

- `runtime_prompts/persona_evaluator.md`
  - Runtime path: `POST /admin/benchmark/evaluate`
  - Provider/client: Anthropic
  - Model in code: `claude-sonnet-4-5`
  - Role: Admin benchmark evaluation of recommendation results through six persona perspectives.

## Excluded

- `planner_agent.py` GPT query-cleaning prompt
  - Reason: The function currently returns `clean_query_rule_based(query)` before the OpenAI call, so that prompt is unreachable in actual runtime.

- `conversation_agent.py` `BrainFryTextDetector` prompt
  - Reason: The class exists, but the active `/api/chat` flow computes BrainFry from behavioral signals and does not instantiate or call this detector.

- `score_personas.py` persona scoring prompts
  - Reason: This is an offline CLI scoring script, not a service endpoint used by the running customer/admin app.

- `fill_embeddings.py` and `vector_search.py`
  - Reason: These call embedding APIs with text input, but they do not send natural-language LLM prompts.

- Development, debugging, README, paper-writing, and presentation text
  - Reason: These are not runtime Agent prompts.

## Sensitive Data Handling

The documented prompts contain only static templates copied from code. API keys, `.env` values, private user data, persisted chat logs, and real session records are intentionally not included.

