# Triển khai local và GCP GPU VM

Dùng duy nhất [docker-compose.yml](../docker-compose.yml), build source ngay trên máy chạy.
Hướng dẫn: [DOCKER_GCLOUD_GUIDE.md](../docs/DOCKER_GCLOUD_GUIDE.md).

```bash
make docker-up
make local-admin
make docker-ps
```

Stack gồm frontend Nginx, API, worker, embedding GPU, PostgreSQL, Redis, MinIO và Qdrant.
Không cần registry, Cloud Run hoặc file Compose override.
