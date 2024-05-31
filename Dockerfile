FROM python:3.11.5-slim

ENV ADM_PROPERTIES_PATH=/mnt/sslcerts/adm.properties
RUN pip install --upgrade pip
RUN pip install kubernetes==29.0.0 confluent-kafka==2.4.0

COPY . /myWork
WORKDIR /kafka-acl-operator

CMD ["python", "myWork/operator/kafka-acl-operator.py"]
