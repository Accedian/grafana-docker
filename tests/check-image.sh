#!/usr/bin/env bash
set -euo pipefail

image=${1:?Usage: check-image.sh IMAGE}
expected_plugins=${2-xginn8-pagerduty-datasource,grafana-clock-panel,grafana-piechart-panel,grafana-clickhouse-datasource}

# Check the packaged files, including the stock copy used for persistent data.
docker run --rm --network none -e EXPECTED_PLUGINS="$expected_plugins" --entrypoint /bin/sh "$image" -ec '
    for root in /var/lib/grafana/plugins /data/grafana/plugins; do
        if [ -e "$root/grafana-image-renderer" ]; then
            echo "Retired Image Renderer remains in $root" >&2
            exit 1
        fi
        IFS=","; for entry in $EXPECTED_PLUGINS; do
            plugin=$(printf "%s" "$entry" | awk "{print \$1}")
            if [ ! -r "$root/$plugin/plugin.json" ]; then
                echo "Missing bundled plugin: $root/$plugin" >&2
                exit 1
            fi
        done
    done
    case ",${GF_PLUGINS_DISABLE_PLUGINS:-}," in
        *,grafana-image-renderer,*) ;;
        *) echo "Persisted Image Renderer is not disabled by default" >&2; exit 1 ;;
    esac
    echo "Bundled plugins verified; retired Image Renderer is absent and disabled."
'
