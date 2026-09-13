FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY jobhub_agents ./jobhub_agents
EXPOSE 8090
CMD ["uvicorn","jobhub_agents.main:app","--host","0.0.0.0","--port","8090"]
