# preza-inference

Тонкий OpenAI-совместимый чат-клиент (поверх `httpx`) плюс загрузчик `skills/<name>/`.
Общий для `packages/generator` и `packages/audit`, чтобы ни один из них не дублировал
HTTP или разбор YAML/Markdown. Решения по провайдеру/моделям — в `MODELS.md`,
как это встроено в пайплайн — в `ARCHITECTURE.md`.

## Конфигурация

Читает `INFERENCE_API_BASE` / `INFERENCE_API_KEY` из окружения (`.env` в корне
репозитория, см. `.env.example`). `INFERENCE_API_KEY` обязателен на момент вызова —
клиент бросает `RuntimeError`, а не молча ничего не делает и не выдумывает ответ.

## Использование

```python
from inference import InferenceClient, load_skill

skill = load_skill("outline-generation")
client = InferenceClient()
result = client.complete_structured(
    model=skill.model,
    system_prompt=skill.prompt,
    user_content="...",
    temperature=skill.temperature,
    max_tokens=skill.max_tokens,
    response_model=MyPydanticModel,
)
```
