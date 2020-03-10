FROM python:3.8-slim as builder

RUN apt update && apt install -y build-essential
COPY jticker-core/requirements.txt /requirements-core.txt
COPY requirements.txt /
RUN pip install --no-cache-dir -r requirements-core.txt -r requirements.txt

FROM python:3.8-slim as runner

COPY --from=builder /usr/local/lib/python3.8/site-packages/ /usr/local/lib/python3.8/site-packages/

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -e ./jticker-core -e ./

ENTRYPOINT ["python", "-m", "jticker_stats"]
