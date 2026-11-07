"""Keep lab pool/TLS overrides explicit and validate them without a live database."""
from unittest.mock import patch

import pytest

from app.db.mariadb import make_engine


def test_explicit_worker_pool_and_lab_tls_override():
    with patch.dict('os.environ', {'DB_POOL_SIZE': '20', 'DB_MAX_OVERFLOW': '0',
                                  'DB_POOL_TIMEOUT_SECONDS': '5', 'DB_TLS_DISABLED': 'true'}), patch('app.db.mariadb.create_engine') as create:
        make_engine('mysql+pymysql://unused')
    options = create.call_args.kwargs
    assert options['pool_size'] == 20
    assert options['max_overflow'] == 0
    assert options['pool_timeout'] == 5
    assert options['connect_args']['ssl_disabled'] is True


def test_normal_deployment_does_not_disable_tls():
    with patch.dict('os.environ', {'DB_TLS_DISABLED': 'false'}), patch('app.db.mariadb.create_engine') as create:
        make_engine('mysql+pymysql://unused')
    assert 'ssl_disabled' not in create.call_args.kwargs['connect_args']


def test_invalid_pool_limits_fail_before_engine_creation():
    with patch.dict('os.environ', {'DB_POOL_SIZE': '0'}), pytest.raises(ValueError, match='Invalid database pool limits'):
        make_engine('mysql+pymysql://unused')
