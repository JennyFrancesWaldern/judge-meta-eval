.PHONY: setup run report test reproduce label

setup:
	pip install -r requirements.txt

test:
	pytest tests/ -v

label:
	python -m src.labeling_server

run:
	python -m src.run

report:
	python -m src.report

reproduce:
	python -m src.reproduce
