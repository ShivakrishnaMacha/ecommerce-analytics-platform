.PHONY: pipeline app test docker

pipeline:
	python pipeline/run_pipeline.py

pipeline-tiny:
	python pipeline/run_pipeline.py --scale tiny

app:
	streamlit run app.py

test:
	pytest -q

docker:
	docker build -t ecommerce-analytics .
