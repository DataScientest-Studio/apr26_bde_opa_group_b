# Airflow image for ORCHESTRATION ONLY.
#
# The actual jobs (fetch_historical, train_model) do NOT run inside Airflow.
# Each task launches a container from the `cryptobot-app` image via
# DockerOperator. So Airflow needs none of the project's data dependencies
# (pandas, scikit-learn, SQLAlchemy 2.x, …) — which avoids ALL version
# conflicts between Airflow's pins and ours.
FROM apache/airflow:2.10.4-python3.11

# DockerOperator + the docker client live in the Docker provider package.
RUN pip install --no-cache-dir apache-airflow-providers-docker
