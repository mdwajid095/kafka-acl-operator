FROM python:3.11.5-slim

ENV ADM_PROPERTIES_PATH=/mnt/sslcerts/adm.properties

RUN pip install --upgrade pip && \
    pip install kubernetes==29.0.0 confluent-kafka==2.8.0

WORKDIR /home
COPY operator/kafka_acl_operator.py /app/kafka-acl-operator.py

CMD ["python", "/app/kafka-acl-operator.py"]
