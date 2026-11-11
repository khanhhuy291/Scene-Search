# syntax=docker/dockerfile:1.7
FROM golang:1.25-alpine AS build
RUN apk add --no-cache ca-certificates git
# Upstream no longer publishes the community image. Build a fixed source
# revision rather than depending on the removed Docker Hub/Quay tags.
ARG MINIO_VERSION=v0.0.0-20260212201848-7aac2a2c5b7c
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOMAXPROCS=2 go install -p 2 github.com/minio/minio@${MINIO_VERSION}

FROM alpine:3.22
RUN apk add --no-cache ca-certificates curl \
    && addgroup -g 10001 minio && adduser -D -u 10001 -G minio minio \
    && mkdir /data && chown minio:minio /data
COPY --from=build /go/bin/minio /usr/local/bin/minio
USER minio
EXPOSE 9000 9001
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
