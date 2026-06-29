.PHONY: build up logs logs-beat health debug create-db migrate

NAME = reels_automation
DB_CONTAINER_NAME = reels_automation_database
DB_NAME= reels_automation

build:
	docker compose up -d --build

up:
	docker compose up -d

make logs:
	docker compose logs $(NAME) -f --tail 50

logs-beat:
	docker compose logs reels_automation_celery_beat -f --tail 50

health:
	docker compose ps
	docker logs --tail 20 reels_automation_celery_beat

debug:
	docker attach $(NAME)

create-db:
	docker exec -it $(DB_CONTAINER_NAME) createdb -h 127.0.0.1 -U reels $(DB_NAME)

drop-db:
	docker exec -it $(DB_CONTAINER_NAME) dropdb -h 127.0.0.1 -U reels $(DB_NAME)

makemigrations:
	docker exec -it $(NAME) alembic revision --autogenerate -m "$(message)"

migrate:
	docker exec -it $(NAME) alembic upgrade head

stamp:
	docker exec -it $(NAME) alembic stamp head

add-permissions:
	docker exec -it $(NAME) python scripts/add_permissions.py

seed-users:
	docker exec -it $(NAME) python scripts/seed_users.py