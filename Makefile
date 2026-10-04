.PHONY: help build up down restart logs status shell clean

help:
	@echo "Available commands for turntable-bridge:"
	@echo "  make build    - Build Docker image"
	@echo "  make up       - Start container in background"
	@echo "  make down     - Stop and remove container"
	@echo "  make restart  - Restart container"
	@echo "  make logs     - Follow container logs"
	@echo "  make status   - Check live status via API (port 80)"
	@echo "  make shell    - Open bash shell inside container"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

status:
	curl -s http://localhost/api | python3 -m json.tool

shell:
	docker compose exec turntable-bridge bash
