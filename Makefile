.PHONY: setup run report test reproduce

setup:
	pip install -r requirements.txt

test:
	pytest tests/ -v

run:
	python -m src.run

report:
	python -m src.report

reproduce:
	python -m src.reproduce
