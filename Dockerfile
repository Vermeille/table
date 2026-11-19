FROM nousresearch/hermes-agent:v0.22.5
LABEL org.opencontainers.image.title="Table" org.opencontainers.image.version="0.1.0"
USER root
WORKDIR /app
RUN /opt/hermes/tools/uv-*/uv pip install --python /opt/hermes/.venv/bin/python pywebpush==2.5.0
COPY . /app
RUN mkdir -p /table-data && chown 10000:10000 /table-data
ENV PYTHONPATH=/opt/hermes HERMES_HOME=/opt/data TABLE_DATA=/table-data
USER 10000:10000
EXPOSE 8080
ENTRYPOINT ["/opt/hermes/.venv/bin/python","-m","uvicorn","server:app","--host","0.0.0.0","--port","8080","--proxy-headers","--forwarded-allow-ips","*"]
