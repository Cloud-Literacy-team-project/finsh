#!/bin/bash
# Run after deploying code, creating its venv, and writing /opt/finsh/.env.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then
  echo 'Run with sudo bash /opt/finsh/infra/bastion/install.sh' >&2
  exit 1
fi
cd /opt/finsh
test -x .venv/bin/python
test -f .env
command -v flock >/dev/null
getent passwd finsh >/dev/null
chown finsh:finsh .env
chmod 600 .env
runuser -u finsh -- .venv/bin/python - <<'PY'
from engine import iac, safety
from db.database import connect
if not safety.is_dry_run():
    raise SystemExit('Initial cron installation requires FINSH_DRY_RUN=1.')
iac.terraform_nos()
with connect() as conn, conn.cursor() as cur:
    cur.execute("SELECT delete_requested_at FROM trash LIMIT 0")
print('DB and Terraform access verified in dry-run mode.')
PY
install -d -o finsh -g finsh -m 0750 /var/log/finsh
install -o root -g root -m 0755 infra/bastion/finsh /usr/local/bin/finsh
install -o root -g root -m 0644 infra/bastion/finsh-cron /etc/cron.d/finsh
systemctl enable --now cron
echo 'finsh command and cron installed in dry-run mode.'
