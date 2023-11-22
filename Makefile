IMAGE_REPO := gcr.io/npav-172917
IMAGE_NAME := grafana
IMAGE_TAG ?= $(shell whoami)-dev

DOCKER_DEFAULT_PLATFORM := linux/amd64
export DOCKER_DEFAULT_PLATFORM

GRAFANA_VERSION ?= 10.2.2
GRAFANA_URL ?= https://dl.grafana.com/oss/release/grafana_$(GRAFANA_VERSION)_amd64.deb
GOSU_URL ?= https://github.com/tianon/gosu/releases/download/1.17/gosu-amd64

.PHONY: all
all: build

.PHONY: build
build:
	@echo "Building Grafana image: $(IMAGE_REPO)/$(IMAGE_NAME):$(IMAGE_TAG)"
	@echo "Using Grafana URL $(GRAFANA_URL)"
	@echo "Using GOSU URL $(GOSU_URL)"
	docker build \
        --no-cache=true \
        --build-arg "GRAFANA_URL=$(GRAFANA_URL)" \
        --build-arg "GOSU_URL=$(GOSU_URL)" \
        --tag "$(IMAGE_REPO)/$(IMAGE_NAME):$(IMAGE_TAG)" \
        .

push: build
	docker push "$(IMAGE_REPO)/$(IMAGE_NAME):$(IMAGE_TAG)"
