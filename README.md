# jianzhu-saas - Building Inspection SaaS API

Enterprise-grade building inspection and structural assessment SaaS platform.

## Features

- **API-first architecture**: RESTful API for building inspection data
- **MLP risk scoring**: Machine learning prediction for structural risk
- **Compliance checking**: Automated code compliance verification
- **Report generation**: PDF/HTML inspection reports
- **Multi-tenant**: Isolated data per organization

## Quick Start

```bash
pip install flask
python api_server.py
```

## API Endpoints

### Health Check
```
GET /health
```

### Create Inspection
```
POST /api/inspections
Content-Type: application/json

{
  "building_id": "BLD-001",
  "inspector": "Zhang Wei",
  "type": "structural",
  "findings": [...]
}
```

### Get Inspection
```
GET /api/inspections/<id>
```

### Risk Assessment
```
POST /api/assessments
Content-Type: application/json

{
  "building_id": "BLD-001",
  "metrics": {
    "concrete_strength_mpa": 25,
    "rebar_cover_mm": 25,
    "crack_width_mm": 0.2
  }
}
```

## Configuration

```env
FLASK_HOST=0.0.0.0
FLASK_PORT=8080
SECRET_KEY=your-secret-key
DATABASE_URL=sqlite:///inspections.db
```

## Deployment

### Docker
```dockerfile
FROM python:3.11-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
EXPOSE 8080
CMD ["python", "api_server.py"]
```

### Cloud
- AWS ECS / GCP Cloud Run / Aliyun SAE
- Minimum: 1 vCPU, 512MB RAM

## License

MIT
