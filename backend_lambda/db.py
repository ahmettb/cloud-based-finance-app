import psycopg2
from psycopg2 import pool

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER, RUN_DB_MIGRATIONS_ON_START, logger, ssm_client

db_pool = None
migration_checked = False


def init_db_pool():
    global db_pool, DB_PASSWORD
    if db_pool is not None:
        return
    logger.info("Initializing DB pool")
    actual_password = DB_PASSWORD
    if actual_password and actual_password.startswith("ssm:"):
        logger.info("Fetching DB_PASSWORD from SSM Parameter Store")
        try:
            resp = ssm_client.get_parameter(Name=actual_password[4:], WithDecryption=True)
            actual_password = resp["Parameter"]["Value"]
        except Exception as e:
            logger.error(f"Failed to fetch DB password from SSM: {e}")
            raise RuntimeError("Secure database credential fetch failed.")
    db_pool = psycopg2.pool.SimpleConnectionPool(
        minconn=1, maxconn=8,
        host=DB_HOST, database=DB_NAME, user=DB_USER,
        password=actual_password, port=DB_PORT, connect_timeout=8,
    )


def get_db_connection():
    if db_pool is None:
        init_db_pool()
    return db_pool.getconn()


def release_db_connection(conn):
    if db_pool and conn:
        db_pool.putconn(conn)


def maybe_run_migrations_once():
    global migration_checked
    if migration_checked or not RUN_DB_MIGRATIONS_ON_START:
        return
    try:
        from migrations import ensure_tables_exist
        ensure_tables_exist()
        migration_checked = True
    except Exception as exc:
        logger.error(f"Migration check failed: {exc}")
