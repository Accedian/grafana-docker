#!/bin/bash

if [ "${_grafana_version}" != "" ]; then
	echo "Building version ${_grafana_version}"
	echo "Download url: https://s3-us-west-2.amazonaws.com/grafana-releases/release/grafana_${_grafana_version}_amd64.deb"
	docker build \
		--build-arg DOWNLOAD_URL=https://s3-us-west-2.amazonaws.com/grafana-releases/release/grafana_${_grafana_version}_amd64.deb \
		--tag "${_docker_repo}grafana:${_docker_version}" \
		--no-cache=true .
	docker tag ${_docker_repo}grafana:${_docker_version} grafana/grafana:latest

else
	echo "Building latest for master"
	docker build \
		--tag "${_docker_repo}grafana:${_docker_version}" \
		--no-cache=true .
fi
