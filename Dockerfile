FROM python:3.11.5-slim

ENV ADM_PROPERTIES_PATH=/mnt/sslcerts/adm.properties

RUN pip install kubernetes==29.0.0 confluent-kafka==2.4.0

COPY . /kafka-acl-operator
WORKDIR /kafka-acl-operator

CMD ["python", "/operator/kafka-acl-operator.py"]
