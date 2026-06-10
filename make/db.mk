.PHONY: migrate
# run any pending database migrations
migrate:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py migrate
else
	docker compose run --rm backend python manage.py migrate
endif

.PHONY: create-user
# create a normal user: make create-user username=<name> password=<pass>
create-user:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py create-user $(username) $(password)
else
	docker compose run --rm backend python manage.py create-user $(username) $(password)
endif

.PHONY: create-admin
# create an admin user: make create-admin username=<name> password=<pass>
create-admin:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py create-user $(username) $(password) --admin
else
	docker compose run --rm backend python manage.py create-user $(username) $(password) --admin
endif

.PHONY: rename-user
# rename a user: make rename-user username=<name> new_username=<new-name>
rename-user:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py rename-user $(username) $(new_username)
else
	docker compose run --rm backend python manage.py rename-user $(username) $(new_username)
endif

.PHONY: delete-user
# delete a user: make delete-user username=<name>
delete-user:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py delete-user $(username)
else
	docker compose run --rm -it backend python manage.py delete-user $(username)
endif

.PHONY: list-users
# list all users
list-users:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py list-users
else
	docker compose run --rm backend python manage.py list-users
endif

.PHONY: reset-db
# delete all boxes, tubes, locations, and history — users are preserved
reset-db:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py reset-db
else
	docker compose run --rm -it backend python manage.py reset-db
endif

.PHONY: db-backup
# dump the database to data/db-backup-<timestamp>.sql
db-backup:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py db-backup
else
	docker compose run --rm backend python manage.py db-backup
endif

.PHONY: db-restore
# restore the database from a backup: make db-restore file=db-backup-<timestamp>.sql
db-restore:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py db-restore $(file)
else
	docker compose run --rm -it backend python manage.py db-restore $(file)
endif

.PHONY: seed
# populate the database with sample data (~15 boxes, ~53 tubes)
seed:
ifdef PYTHONANYWHERE_SITE
	venv/bin/python backend-src/manage.py seed
else
	docker compose run --rm backend python manage.py seed
endif
