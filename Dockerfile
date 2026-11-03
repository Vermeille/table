FROM nousresearch/hermes-agent:v0.22.5
LABEL org.opencontainers.image.title="Table" org.opencontainers.image.version="0.1.0"
USER root
WORKDIR /app
COPY . /app
RUN mkdir -p /table-data && chown 1000:1000 /table-data
ENV PYTHONPATH=/opt/hermes HERMES_HOME=/opt/data TABLE_DATA=/table-data
USER 1000:1000
EXPOSE 8080
ENTRYPOINT ["/opt/hermes/.venv/bin/python","-m","uvicorn","server:app","--host","0.0.0.0","--port","8080","--proxy-headers","--forwarded-allow-ips","*"]
