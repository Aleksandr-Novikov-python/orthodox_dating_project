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