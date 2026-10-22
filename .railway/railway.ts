// Railway Infrastructure as Code: https://docs.railway.com/infrastructure-as-code/reference
// Apply from a linked checkout: DIRECTORY_DOMAIN=... PRODUCTIVITY_DOMAIN=... railway config apply
import { bucket, defineRailway, github, postgres, preserve, project, redis, ref, service } from 'railway/iac';

// Domains are literal strings in the config, so they come from the shell instead of the repo.
function requiredEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Set ${name} in the environment before running railway config`);
  }
  return value;
}

// Virginia for every service; Postgres and Redis follow the account's default region (set it to Virginia first).
const REGION = 'us-east4-eqdc4a';

export default defineRailway(() => {
  const directoryDomain = requiredEnv('DIRECTORY_DOMAIN');
  const productivityDomain = requiredEnv('PRODUCTIVITY_DOMAIN');

  const db = postgres('postgres');
  const cache = redis('redis');
  const media = bucket('media', { region: 'iad' });

  // Deploys wait for the commit's GitHub Actions runs (checkSuites), so a red check never deploys.
  const source = github('alpha-bravo-lima/django-ship', { branch: 'main', checkSuites: true });
  const build = { builder: 'DOCKERFILE' as const };

  // Every service loads project.settings_production, so all three get the same variables.
  // preserve() keeps the value the owner set in the dashboard out of the repo.
  const env = {
    DATABASE_URL: db.env.DATABASE_URL,
    REDIS_URL: cache.env.REDIS_URL,
    AWS_STORAGE_BUCKET_NAME: ref(media, 'BUCKET'),
    AWS_ACCESS_KEY_ID: ref(media, 'ACCESS_KEY_ID'),
    AWS_SECRET_ACCESS_KEY: ref(media, 'SECRET_ACCESS_KEY'),
    AWS_S3_ENDPOINT_URL: ref(media, 'ENDPOINT'),
    AWS_S3_REGION_NAME: ref(media, 'REGION'),
    ALLOWED_HOSTS: `${directoryDomain},${productivityDomain}`,
    DIRECTORY_DOMAIN: directoryDomain,
    PRODUCTIVITY_DOMAIN: productivityDomain,
    SECRET_KEY: preserve(),
    ADMINS: preserve(),
    DEFAULT_FROM_EMAIL: preserve(),
    SERVER_EMAIL: preserve(),
    DIRECTORY_FROM_EMAIL: preserve(),
    PRODUCTIVITY_FROM_EMAIL: preserve(),
    STRIPE_LIVE_MODE: preserve(),
    STRIPE_TEST_SECRET_KEY: preserve(),
    STRIPE_LIVE_SECRET_KEY: preserve(),
    DIRECTORY_STRIPE_PORTAL_CONFIGURATION: preserve(),
    PRODUCTIVITY_STRIPE_PORTAL_CONFIGURATION: preserve(),
    POSTMARK_SERVER_TOKEN: preserve(),
    SENTRY_DSN: preserve(),
    TURNSTILE_KEY: preserve(),
    TURNSTILE_SECRET: preserve(),
  };

  const web = service('web', {
    source,
    build,
    env,
    domains: [directoryDomain, productivityDomain],
    deploy: {
      startCommand: 'gunicorn project.wsgi --bind 0.0.0.0:$PORT',
      preDeployCommand: ['./deploy/pre_deploy.sh'],
      healthcheckPath: '/health/',
      region: REGION,
    },
  });

  const worker = service('worker', {
    source,
    build,
    env,
    deploy: { startCommand: 'celery -A project worker -l info', region: REGION },
  });

  // One replica only: django_celery_beat's DatabaseScheduler would schedule every task once per replica.
  const beat = service('beat', {
    source,
    build,
    env,
    deploy: { startCommand: 'celery -A project beat -l info', numReplicas: 1, region: REGION },
  });

  return project('django-ship', { resources: [db, cache, media, web, worker, beat] });
});
