# tests/backend/test_auth.py


def test_admin_login_success(client):
    response = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert response.json()["token_type"] == "bearer"


def test_admin_login_wrong_password(client):
    response = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "WrongPassword123!"
        }
    )
    assert response.status_code == 401