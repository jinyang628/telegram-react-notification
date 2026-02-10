.PHONY: lint

lint:
	black .
	isort .
	autoflake --in-place --recursive --remove-all-unused-imports .

start:
	python main.py
