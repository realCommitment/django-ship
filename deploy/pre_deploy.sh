#!/usr/bin/env bash
# Railway pre-deploy command on the web service: runs in its own container from the new image, before it starts.
# A non-zero exit stops the deploy. https://docs.railway.com/deployments/pre-deploy-command
set -o errexit

python manage.py migrate --noinput
python manage.py sync_sites
python manage.py bootstrap_celery_tasks
