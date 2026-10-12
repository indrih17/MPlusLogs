FROM python:3.12-slim
WORKDIR /app
COPY tools/api_budget.py tools/build_database.py tools/clipboard_companion.py tools/profile_server.py tools/profile_service.py tools/realm_resolver.py tools/wcl_sync.py ./tools/
COPY realm-slugs.json ./
RUN useradd --uid 10001 --create-home mpluslogs && mkdir /data && chown mpluslogs /data
USER 10001:10001
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 MPLUSLOGS_DATA=/data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/healthz', timeout=3).read()"
CMD ["python", "tools/profile_server.py"]
