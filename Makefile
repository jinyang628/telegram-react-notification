.PHONY: lint

lint:
	black .
	isort .
	autoflake --in-place --recursive .

start:
	python main.py
