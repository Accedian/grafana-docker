DOCKER_REPO_NAME:= gcr.io/npav-172917/
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
BUILD_PLATFORMS ?= linux/amd64 #linux/arm64/v8 remove arm64 from list because plugin not supported

GRAFANA_VERSION ?= 11.5.0
GRAFANA_URL ?= https://dl.grafana.com/oss/release/grafana_$(GRAFANA_VERSION)
GOSU_URL ?= https://github.com/tianon/gosu/releases/download/1.17/gosu
GF_INSTALL_PLUGINS ?= "xginn8-pagerduty-datasource,grafana-image-renderer 3.7.2,grafana-clock-panel,grafana-piechart-panel,grafana-clickhouse-datasource"

# Add the following for helm chart
SEMVER_PATTERN := ^[0-9]+\.[0-9]+\.[0-9]+
HELM_VER ?= $(shell if echo "$(DOCKER_VER)" | grep -Eq '$(SEMVER_PATTERN)'; then echo "$(DOCKER_VER)"; else echo "0.0.0-$(DOCKER_VER)"; fi)
HELM_REPO := oci://us-docker.pkg.dev/npav-172917/helm-package

.PHONY: all
all: build

.PHONY: build

docker:
	@echo "Building Grafana image: $(IMAGE_REPO)/$(IMAGE_NAME):$(IMAGE_TAG)"
	@echo "Using Grafana URL $(GRAFANA_URL)"
	@echo "Using GOSU URL $(GOSU_URL)"
	docker buildx build --no-cache --build-arg GRAFANA_VERSION=$(GRAFANA_VERSION) --build-arg VERSION=$(DOCKER_VER) --build-arg GF_INSTALL_PLUGINS=$(GF_INSTALL_PLUGINS) --platform $(LOCAL_BUILD_PLATFORM) -t $(DOCKER_REPO_NAME)$(DOCKER_IMAGE_NAME):$(DOCKER_VER) --load .

push: 
	@echo "building with $(BUILD_PLATFORMS)"
	@echo "Building Grafana image: $(IMAGE_REPO)/$(IMAGE_NAME):$(IMAGE_TAG)"
	@echo "Using Grafana URL $(GRAFANA_URL)"
	@echo "Using GOSU URL $(GOSU_URL)"
	docker buildx build --build-arg GRAFANA_VERSION=$(GRAFANA_VERSION) --build-arg VERSION=$(DOCKER_VER) --build-arg GF_INSTALL_PLUGINS=$(GF_INSTALL_PLUGINS) --platform $(BUILD_PLATFORMS) -t $(DOCKER_REPO_NAME)$(DOCKER_IMAGE_NAME):$(DOCKER_VER) --push .

.FORCE: 


helm/%.yaml: helm/%.yaml.in .FORCE
	@echo "# /!\ This file is generated, do not edit!" > $@
	sed -e "s/@HELM_VER@/$(HELM_VER)/" $< >> $@

helm-lint: helm/Chart.yaml helm/values.yaml
	helm lint helm

helm $(DOCKER_IMAGE_NAME)-$(HELM_VER).tgz: .FORCE helm-lint helm/Chart.yaml helm/values.yaml
	@echo "Using 'version: $(HELM_VER)'"
	helm package helm

helm-push: $(DOCKER_IMAGE_NAME)-$(HELM_VER).tgz
	helm push $< $(HELM_REPO)
