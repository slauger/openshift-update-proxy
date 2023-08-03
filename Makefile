IMAGE_NAME=quay.io/slauger/openshift-update-proxy

HTTP_PROXY?=http://localhost:3128

build:
	docker build -t $(IMAGE_NAME) .

test:
	docker run -v /var/run/docker.sock:/var/run/docker.sock -v $(shell pwd):/src:ro gcr.io/gcp-runtimes/container-structure-test:latest test --image $(CONTAINER_NAME):$(CONTAINER_TAG) --config /src/tests/image.tests.yaml

run:
	docker run -p 5000:5000 -e HTTP_PROXY=$(HTTP_PROXY) -it $(IMAGE_NAME)

push:
	docker push $(IMAGE_NAME)
