FROM python:3.11.5-slim

ENV ADM_PROPERTIES_PATH=/mnt/sslcerts/adm.properties

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        librdkafka1 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/

RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
      kubernetes==33.1.0 \
      confluent-kafka==2.11.1

WORKDIR /home
COPY operator/kafka_acl_operator.py /app/kafka-acl-operator.py

CMD ["python", "-u", "/app/kafka-acl-operator.py"]
