"""
DAG: cryptobot_train
====================
Once a day: first catch the data up (fetch_historical), THEN retrain the model
(train_model). Two tasks run in sequence inside cryptobot-app containers:

    fetch_historical  ->  train_model

train_model writes models/model.pkl. That path is a SHARED Docker volume
(cryptobot_models) also mounted by the API container, so the API serves the
freshly retrained model on its next /predict — no restart needed
(predict_model re-reads the file each call). This mirrors how you'd share the
model via S3 on AWS.
"""
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

TASK_ENV = {
    "POSTGRES_HOST": "postgres",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": os.environ.get("POSTGRES_USER"),
    "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
    "POSTGRES_DB": os.environ.get("POSTGRES_DB"),
}

# Mount the shared model volume so the retrained model.pkl reaches the API.
MODEL_MOUNT = Mount(source="cryptobot_models", target="/app/models", type="volume")

default_args = {"retries": 1, "retry_delay": timedelta(minutes=5)}

with DAG(
    dag_id="cryptobot_train",
    description="Catch up data, then retrain the model (daily)",
    schedule="0 0 * * *",             # daily at 00:00
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["cryptobot"],
) as dag:
    fetch = DockerOperator(
        task_id="fetch_historical",
        image="cryptobot-app",
        command="python -m src.collection.fetch_historical",
        environment=TASK_ENV,
        network_mode="cryptobot_network",
        auto_remove="success",
        mount_tmp_dir=False,
    )

    train = DockerOperator(
        task_id="train_model",
        image="cryptobot-app",
        command="python -m src.models.train_model",
        environment=TASK_ENV,
        network_mode="cryptobot_network",
        mounts=[MODEL_MOUNT],         # write the new model.pkl to the shared volume
        auto_remove="success",
        mount_tmp_dir=False,
    )

    fetch >> train                    # train runs only after fetch succeeds
