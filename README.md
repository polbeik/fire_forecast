# Fire Forecast
Microservice platform for spatio-temporal wildfire segmentation, operational hindcasting, counterfactual fire scenarios, and fire-spread model comparison.

Core modes:
- Burned-area segmentation on FLOGA.
- Operational hindcast using archived forecast weather where available.
- Historical actual-weather replay.
- Counterfactual ignition scenarios.
- ML / PINN / Hybrid / physics-simulator comparison.

Local runtime:
- API Gateway: http://localhost:8000
- Catalog service: http://localhost:8101
- Ingestion service: http://localhost:8102
- Preprocessing service: http://localhost:8103
- Segmentation service: http://localhost:8104
- Forecasting service: http://localhost:8105
- PINN service: http://localhost:8106
- Simulation adapter service: http://localhost:8107
- Visualization service: http://localhost:8108
- Plugin adapter service: http://localhost:8109
- NATS monitor: http://localhost:8222
- MinIO console: http://localhost:9001
- Prefect server: http://localhost:4202
