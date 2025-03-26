
image_name := "envoy-extproc-sdk-python"
image_tag := `git rev-parse HEAD`
generated_code := "generated/python/standardproto"

install: python-install codegen

update: python-update buf-update codegen

python-install:
    uv sync

python-update:
    uv sync --upgrade

buf-update:
    buf mod update

codegen:
    bash scripts/remove_generated_code.sh
    buf -v generate buf.build/cncf/xds
    buf -v generate buf.build/envoyproxy/envoy
    buf -v generate buf.build/envoyproxy/protoc-gen-validate
    buf -v generate https://github.com/grpc/grpc.git --path src/proto/grpc/health/v1/health.proto
    bash scripts/fix_grpc_health_proto.sh
    bash scripts/install_generated_code.sh

format:
    uv run isort envoy_extproc_sdk examples tests
    uv run black envoy_extproc_sdk examples tests
    uv run flake8 envoy_extproc_sdk examples tests

types:
    uv run mypy envoy_extproc_sdk examples tests

check-format:
    uv run isort envoy_extproc_sdk examples tests --check
    uv run black envoy_extproc_sdk examples tests --check
    uv run flake8 envoy_extproc_sdk examples tests

unit-test: 
    DD_TRACE_ENABLED=false \
        uv run python -m pytest -v tests/unit

integration-test: 
    DD_TRACE_ENABLED=false \
        uv run python -m pytest tests/integration

coverage: 
    DD_TRACE_ENABLED=false \
        uv run coverage run -m pytest -v tests/unit \
            --junitxml=test-results/junit.xml
    uv run coverage report -m

run service="envoy_extproc_sdk.BaseExtProcService":
    uv run python -m envoy_extproc_sdk --service {{service}} --logging

build:
    docker build . -t {{image_name}}:{{image_tag}}
    docker build . -f examples/Dockerfile \
        --build-arg IMAGE_TAG=$(IMAGE_TAG) \
        -t {{image_name}}-examples:{{image_tag}}

up:
    docker compose up --build

down:
    docker compose down --volumes

package:
    uv pip build

publish:
    uv pip publish --build
