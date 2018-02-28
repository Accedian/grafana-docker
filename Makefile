DOCKER_REPO_NAME:= gcr.io/npav-172917/
DOCKER_IMAGE_NAME := grafana	 
DOCKER_VER := $(if $(DOCKER_VER),$(DOCKER_VER),dev)

all: docker
docker:
	export _docker_repo=${DOCKER_REPO_NAME}; export _grafana_version=${GRAFANA_VERSION}; export _docker_version=${DOCKER_VER}; ./build.sh 

push: docker
	docker push $(DOCKER_REPO_NAME)$(DOCKER_IMAGE_NAME):$(DOCKER_VER)
