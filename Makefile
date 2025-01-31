DOCKER_REPO_NAME:= gcr.io/npav-172917
DOCKER_DEVHUB_REPO_NAME:= artifactory.devhub-cloud.cisco.com/acc-skylight-docker/
DOCKER_IMAGE_NAME := grafana

DOCKER_VER := $(if $(DOCKER_VER),$(DOCKER_VER),$(shell whoami)-dev)
BINARY_VER := $(if $(BINARY_VER),$(BINARY_VER),$(shell whoami)-dev)

GO_SDK_IMAGE := golang:1.22.1-alpine
PROJECT_BASE_PATH := $(PWD)
SEMVER := $(shell cat current-version)

GOPATH := $(GOPATH)

UNAME := $(shell uname -m)
LOCAL_BUILD_PLATFORM := linux/amd64
ifeq ($(UNAME),arm64)
	LOCAL_BUILD_PLATFORM = linux/arm64/v8
endif
BUILD_PLATFORMS ?= linux/amd64,linux/arm64/v8

GRAFANA_VERSION ?= 11.5.0
GRAFANA_URL ?= https://dl.grafana.com/oss/release/grafana_$(GRAFANA_VERSION)_amd64.deb
GOSU_URL ?= https://github.com/tianon/gosu/releases/download/1.17/gosu-amd64

.PHONY: all
all: build

.PHONY: build

docker:
	@echo "Building Grafana image: $(IMAGE_REPO)/$(IMAGE_NAME):$(IMAGE_TAG)"
	@echo "Using Grafana URL $(GRAFANA_URL)"
	@echo "Using GOSU URL $(GOSU_URL)"
	docker buildx build --build-arg VERSION=$(DOCKER_VER) --platform $(LOCAL_BUILD_PLATFORM) -t $(DOCKER_REPO_NAME)$(DOCKER_IMAGE_NAME):$(DOCKER_VER) --load .

push: 
	echo "building with $(BUILD_PLATFORMS)"
	docker buildx build --build-arg VERSION=$(DOCKER_VER) --platform $(BUILD_PLATFORMS) -t $(DOCKER_REPO_NAME)$(DOCKER_IMAGE_NAME):$(DOCKER_VER) --push .
