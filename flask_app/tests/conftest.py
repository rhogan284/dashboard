import pytest
from app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING': True, 'DATA_DIR': tmp_path})


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def data_dir(app):
    return app.config['DATA_DIR']
