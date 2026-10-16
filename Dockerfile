FROM python:3.11-slim
WORKDIR /app
COPY . .
# MVP 无第三方依赖；如需 PG/PYJWT 再 pip install -r requirements.txt
ENV JZ_SAAS_DB=/data/jianzhu_saas.db JZ_SAAS_PORT=8080
EXPOSE 8080
VOLUME /data
CMD ["python", "api_server.py"]
