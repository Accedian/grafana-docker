#!/bin/bash
set -euo pipefail

repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
tmp_dir=$(mktemp -d)
trap 'rm -rf "$tmp_dir"' EXIT
chmod 0755 "$tmp_dir"

data_dir=$tmp_dir/data
outside_dir=$tmp_dir/outside
mkdir -m 0770 "$data_dir" "$outside_dir"
chgrp 0 "$data_dir" "$outside_dir"

# Model sensitive content already present on a PVC. Startup must not make it
# accessible to another UID merely because that UID is a member of GID 0.
printf 'secret\n' > "$data_dir/grafana.db"
chmod 0600 "$data_dir/grafana.db"
printf 'outside\n' > "$outside_dir/secret.log"
chmod 0600 "$outside_dir/secret.log"
ln -s "$outside_dir" "$data_dir/logs"

printf '[server]\n' > "$data_dir/grafana.ini"
chmod 0660 "$data_dir/grafana.ini"
chgrp 0 "$data_dir/grafana.ini"

cat > "$tmp_dir/grafana-server" <<'EOF'
#!/bin/bash
set -e
printf 'runtime\n' > "$GF_PATHS_DATA/runtime-created"
EOF
chmod 0755 "$tmp_dir/grafana-server"

run_as_random_uid() {
    local uid=$1
    setpriv --reuid="$uid" --regid=0 --clear-groups \
        env \
        DONT_COPY_STOCK_DASHBOARDS=1 \
        GF_PATHS_DATA="$data_dir" \
        GF_PATHS_LOGS="$data_dir/logs" \
        GF_PATHS_PLUGINS="$data_dir/plugins" \
        GF_PATHS_PROVISIONING="$data_dir/provisioning" \
        GF_PATHS_CONFIG="$data_dir/grafana.ini" \
        GRAFANA_SERVER_BIN="$tmp_dir/grafana-server" \
        "$repo_dir/run.sh"
}

run_as_random_uid 12345

test "$(stat -c %a "$data_dir/grafana.db")" = 600
test "$(stat -c %a "$outside_dir/secret.log")" = 600
test "$(stat -c %a "$data_dir/runtime-created")" = 660

# A co-resident process in GID 0 still cannot read pre-existing owner-only data.
if setpriv --reuid=23456 --regid=0 --clear-groups cat "$data_dir/grafana.db" >/dev/null 2>&1; then
    echo 'pre-existing owner-only data became readable' >&2
    exit 1
fi

# A restarted OpenShift container with another arbitrary UID can use files
# created under the shared GID 0 model.
setpriv --reuid=23456 --regid=0 --clear-groups \
    sh -c 'printf "restart\n" >> "$1"' sh "$data_dir/runtime-created"
run_as_random_uid 23456

echo 'permission checks passed'
