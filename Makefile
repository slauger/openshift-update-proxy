IMAGE_NAME=ghcr.io/slauger/openshift-update-proxy
IMAGE_TAG?=latest
CONTAINER_ENGINE?=docker

HTTPS_PROXY?=

.PHONY: venv test lint build run push test-image

venv:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest --cov=src --cov-report=term-missing

lint:
	.venv/bin/ruff check src/ tests/
	.venv/bin/black --check src/ tests/
	.venv/bin/mypy src/

build:
	$(CONTAINER_ENGINE) build -f Containerfile -t $(IMAGE_NAME):$(IMAGE_TAG) .

run:
	$(CONTAINER_ENGINE) run --rm -p 5000:5000 -e HTTPS_PROXY=$(HTTPS_PROXY) -it $(IMAGE_NAME):$(IMAGE_TAG)

push:
	$(CONTAINER_ENGINE) push $(IMAGE_NAME):$(IMAGE_TAG)

test-image:
	$(CONTAINER_ENGINE) run --rm -v /var/run/docker.sock:/var/run/docker.sock -v $(shell pwd):/src:ro gcr.io/gcp-runtimes/container-structure-test:latest test --image $(IMAGE_NAME):$(IMAGE_TAG) --config /src/tests/image.tests.yaml
