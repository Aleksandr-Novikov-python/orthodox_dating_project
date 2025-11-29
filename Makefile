up:
	@docker-compose up --build

down:
	@docker-compose down -v

restart:
	@docker-compose down -v && docker-compose up --build

logs:
	@docker-compose logs -f

migrate:
	@docker-compose exec web python manage.py migrate

createsu:
	@docker-compose exec web python manage.py createsuperuser

shell:
	@docker-compose exec web python manage.py shell

collectstatic:
	@docker-compose exec web python manage.py collectstatic --noinput

flower:
	@xdg-open http://localhost:5555

web:
	@xdg-open http://localhost:8000

ps:
	@docker-compose ps

test:
	@docker-compose exec web python manage.py test

clean:
	@docker system prune -f

pipcheck:
	@docker-compose exec web pip check

BUILDX_VERSION=0.17.1

buildx-install:
	mkdir -p ~/.docker/cli-plugins
	curl -L https://github.com/docker/buildx/releases/download/v$(BUILDX_VERSION)/buildx-v$(BUILDX_VERSION).linux-amd64 \
		-o ~/.docker/cli-plugins/docker-buildx
	chmod +x ~/.docker/cli-plugins/docker-buildx


#source venv/bin/activate

# ✅ Как использовать
# make up — запустить проект

# make down — остановить и удалить контейнеры

# make restart — перезапустить всё

# make logs — смотреть логи

# make migrate — применить миграции

# make createsu — создать суперпользователя

# make shell — открыть Django shell

# make collectstatic — собрать статику

# make flower — открыть Flower в браузере

# make web — открыть сайт

# make buildx-install