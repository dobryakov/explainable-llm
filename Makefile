.PHONY: up down eval record-fixtures logs clean test dev

# Поднять стек в fixture-режиме (по умолчанию, офлайн, без ключа).
up:
	docker compose up --build

# С публикацией внутренних портов на хост (отладка).
dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

down:
	docker compose down

# Прогон всех демо-задач, сводная таблица верности blind vs grounded (эскиз §4, §7).
# Завершается с кодом 1, если разрыв grounded-blind < CI_GAP_THRESHOLD (эскиз §12.5).
eval:
	docker compose run --rm --no-deps gateway python -m gateway.eval

# Перезапись fixtures/ реальными ответами (трассы агента + ответы нарратора).
# Запускается вручную, требует OPENROUTER_API_KEY (эскиз §12.6).
record-fixtures:
	LLM_MODE=live docker compose run --rm agent-runtime python -m agent_runtime.record_fixtures
	LLM_MODE=live docker compose run --rm narrator python -m narrator.record_fixtures

logs:
	docker compose logs -f

test:
	docker compose run --rm --no-deps audit python -m pytest -q

clean:
	docker compose down -v
