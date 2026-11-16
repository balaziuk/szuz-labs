FROM python:3.12-slim
WORKDIR /labs/16
COPY 9/data /labs/9/data
COPY 13/data /labs/13/data
COPY 15 /labs/15
COPY 16 /labs/16
ENV SZUZ_LABS=/labs
ENV PYTHONPATH=/labs/16:/labs/15
CMD ["python", "demo/run_demo.py"]
