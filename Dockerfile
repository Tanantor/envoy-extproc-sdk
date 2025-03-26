FROM python:3.9-slim AS base

SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get -y upgrade \
    && apt-get -y install --no-install-recommends curl python3-dev gcc \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get -y clean

# https://github.com/grpc-ecosystem/grpc-health-probe/#example-grpc-health-checking-on-kubernetes
RUN GRPC_HEALTH_PROBE_VER=v0.3.1 \
    && GRPC_HEALTH_PROBE_URL=https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VER}/grpc_health_probe-linux-amd64 \
    && curl ${GRPC_HEALTH_PROBE_URL} -L -s -o /bin/grpc_health_probe \
    && chmod +x /bin/grpc_health_probe

FROM base AS build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=100 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/opt/.venv/bin/python3.9 \
    UV_PROJECT_ENVIRONMENT=/opt/.venv

WORKDIR /envoy_extproc_sdk

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.6.8 /uv /usr/local/bin/uv

# Create virtual environment
RUN python -m venv /opt/.venv
ENV PATH="/opt/.venv/bin:$PATH"

# Install dependencies
RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync \
        --locked \
        --no-dev \
        --no-install-workspace

# Copy source code and generated protobuf files
COPY . .
COPY ./envoy_extproc_sdk ./envoy_extproc_sdk
COPY generated/python/standardproto/ ./

# Sync the project
RUN --mount=type=cache,target=/root/.cache \
    uv sync \
        --locked \
        --no-dev \
        --no-editable

FROM base AS final

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/.venv/bin:$PATH"

WORKDIR /envoy_extproc_sdk

# Copy virtual environment from build stage
COPY --from=build /opt/.venv /opt/.venv

# Copy source code and generated protobuf files
COPY --from=build /envoy_extproc_sdk/envoy_extproc_sdk ./envoy_extproc_sdk
COPY --from=build /envoy_extproc_sdk/generated ./generated

ARG GRPC_PORT=50051
EXPOSE ${GRPC_PORT}

ENTRYPOINT ["python","-m","envoy_extproc_sdk"]
