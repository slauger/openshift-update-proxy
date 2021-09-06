IMAGE_NAME=quay.io/slauger/openshift-update-proxy

HTTP_PROXY?=http://localhost:3128

build:
	docker build -t $(IMAGE_NAME) .

run:
	docker run -p 5000:5000 -e HTTP_PROXY=$(HTTP_PROXY) -it $(IMAGE_NAME)

push:
	docker push $(IMAGE_NAME)
