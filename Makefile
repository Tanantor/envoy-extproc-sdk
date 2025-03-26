IMAGE_NAME=envoy-extproc-sdk-python
IMAGE_TAG=`git rev-parse HEAD`
GENERATED_CODE=generated/python/standardproto
SERVICE=envoy_extproc_sdk.BaseExtProcService

.PHONY: install
install: python-install codegen

.PHONY: update
update: python-update buf-update codegen

.PHONY: python-install
python-install:
	uv sync

.PHONY: python-update
python-update:
	uv sync --upgrade

.PHONY: buf-update 
buf-update:
	buf mod update

.PHONY: codegen
codegen:
	bash scripts/remove_generated_code.sh
	buf -v generate buf.build/cncf/xds
	buf -v generate buf.build/envoyproxy/envoy
	buf -v generate buf.build/envoyproxy/protoc-gen-validate
	buf -v generate https://github.com/grpc/grpc.git --path src/proto/grpc/health/v1/health.proto
	bash scripts/fix_grpc_health_proto.sh
	bash scripts/install_generated_code.sh

.PHONY: format
format:
	uv run isort envoy_extproc_sdk examples tests
	uv run black envoy_extproc_sdk examples tests
	uv run flake8 envoy_extproc_sdk examples tests

.PHONY: types
types:
	uv run mypy envoy_extproc_sdk examples tests

.PHONY: lint
check-format:
	uv run isort envoy_extproc_sdk examples tests --check
	uv run black envoy_extproc_sdk examples tests --check
	uv run flake8 envoy_extproc_sdk examples tests

.PHONY: unit-test
unit-test: 
	DD_TRACE_ENABLED=false \
		uv run pytest -v tests/unit

.PHONY: integration-test
integration-test: up-test
	sleep 5
	DD_TRACE_ENABLED=false \
		uv run pytest -v tests/integration

.PHONY: coverage
coverage: 
	DD_TRACE_ENABLED=false \
		uv run coverage run -m pytest -v tests/unit \
			--junitxml=test-results/junit.xml
	uv run coverage report -m

.PHONY: run
run:
	uv run python -m envoy_extproc_sdk --service $(SERVICE) --logging

.PHONY: build
build:
	docker build . -t $(IMAGE_NAME):$(IMAGE_TAG)
	docker build . -f examples/Dockerfile \
		--build-arg IMAGE_TAG=$(IMAGE_TAG) \
		-t $(IMAGE_NAME)-examples:$(IMAGE_TAG)

.PHONY: build-base
build-base:
	docker compose build base

.PHONY: up
up: build-base
	docker compose up --build

.PHONY: down
down:
	docker compose down --volumes

.PHONY: up-test
up-test: build-base
	docker compose up --build -d

.PHONY: down-test
down-test:
	docker compose down --volumes

.PHONY: integration-test-local
integration-test-local: 
	DD_TRACE_ENABLED=false \
		uv run pytest -v tests/integration

.PHONY: test
test: unit-test integration-test down-test

.PHONY: test-flake-finder
test-flake-finder:
	@uv run pytest tests/unit --flake-finder
	@uv run pytest tests/integration --flake-finder

.PHONY: package
package:
	uv pip build

.PHONY: publish
publish:
	uv pip publish --build