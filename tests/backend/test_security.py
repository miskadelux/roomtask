def test_ticket_list_requires_authentication(client):
    response = client.get("/api/tickets")

    assert response.status_code == 401


def test_worker_cannot_access_admin_users(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )

    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    create_response = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": "testworker",
            "password": "TestWorkerPassword123!",
            "role": "worker"
        }
    )

    assert create_response.status_code == 200

    worker_login = client.post(
        "/api/auth/login",
        json={
            "username": "testworker",
            "password": "TestWorkerPassword123!"
        }
    )

    assert worker_login.status_code == 200

    worker_headers = {
        "Authorization": f"Bearer {worker_login.json()['access_token']}"
    }

    response = client.get(
        "/api/admin/users",
        headers=worker_headers
    )

    assert response.status_code == 403


def test_worker_cannot_create_room(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    create_response = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": "roomworker",
            "password": "RoomWorkerPassword123!",
            "role": "worker"
        }
    )

    assert create_response.status_code == 200

    worker_login = client.post(
        "/api/auth/login",
        json={
            "username": "roomworker",
            "password": "RoomWorkerPassword123!"
        }
    )

    worker_headers = {
        "Authorization": f"Bearer {worker_login.json()['access_token']}"
    }

    response = client.post(
        "/api/admin/rooms",
        headers=worker_headers,
        json={"name": "Test room"}
    )

    assert response.status_code == 403


def test_admin_can_create_room(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )

    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    response = client.post(
        "/api/admin/rooms",
        headers=admin_headers,
        json={"name": "Admin Test Room"}
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] > 0
    assert data["name"] == "Admin Test Room"
    assert data["qr_token"]



def test_admin_cannot_claim_worker_ticket(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )

    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    room_response = client.post(
        "/api/admin/rooms",
        headers=admin_headers,
        json={"name": "Claim Test Room"}
    )

    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    ticket_response = client.post(
        "/api/public/reports",
        data={
            "kind": "fault",
            "room_id": str(room_id),
            "title": "Test issue",
            "description": "This is a test issue"
        }
    )

    assert ticket_response.status_code == 200
    ticket_id = ticket_response.json()["ticket_id"]

    claim_response = client.post(
        f"/api/tickets/{ticket_id}/claim",
        headers=admin_headers
    )

    assert claim_response.status_code == 403



def test_worker_can_claim_ticket(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )

    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    create_user = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": "claimworker",
            "password": "ClaimWorkerPassword123!",
            "role": "worker"
        }
    )

    assert create_user.status_code == 200

    worker_login = client.post(
        "/api/auth/login",
        json={
            "username": "claimworker",
            "password": "ClaimWorkerPassword123!"
        }
    )

    assert worker_login.status_code == 200

    worker_headers = {
        "Authorization": f"Bearer {worker_login.json()['access_token']}"
    }

    room_response = client.post(
        "/api/admin/rooms",
        headers=admin_headers,
        json={"name": "Worker Claim Test Room"}
    )

    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    ticket_response = client.post(
        "/api/public/reports",
        data={
            "kind": "fault",
            "room_id": str(room_id),
            "title": "Worker claim test",
            "description": "Testing worker claim functionality"
        }
    )

    assert ticket_response.status_code == 200
    ticket_id = ticket_response.json()["ticket_id"]

    claim_response = client.post(
        f"/api/tickets/{ticket_id}/claim",
        headers=worker_headers
    )

    assert claim_response.status_code == 200
    assert claim_response.json()["ok"] is True
    assert claim_response.json()["ticket_id"] == ticket_id

    ticket_check = client.get(
        f"/api/tickets/{ticket_id}",
        headers=worker_headers
    )

    assert ticket_check.status_code == 200
    assert ticket_check.json()["status"] == "in_progress"



def test_worker_cannot_claim_second_active_ticket(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )

    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    create_user = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": "singleworker",
            "password": "SingleWorkerPassword123!",
            "role": "worker"
        }
    )

    assert create_user.status_code == 200

    worker_login = client.post(
        "/api/auth/login",
        json={
            "username": "singleworker",
            "password": "SingleWorkerPassword123!"
        }
    )

    assert worker_login.status_code == 200

    worker_headers = {
        "Authorization": f"Bearer {worker_login.json()['access_token']}"
    }

    room_response = client.post(
        "/api/admin/rooms",
        headers=admin_headers,
        json={"name": "Single Assignment Test Room"}
    )

    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    ticket_ids = []

    for number in range(1, 3):
        response = client.post(
            "/api/public/reports",
            data={
                "kind": "fault",
                "room_id": str(room_id),
                "title": f"Assignment test {number}",
                "description": f"Unique assignment test issue number {number}"
            }
        )

        assert response.status_code == 200
        ticket_ids.append(response.json()["ticket_id"])

    first_claim = client.post(
        f"/api/tickets/{ticket_ids[0]}/claim",
        headers=worker_headers
    )

    assert first_claim.status_code == 200

    second_claim = client.post(
        f"/api/tickets/{ticket_ids[1]}/claim",
        headers=worker_headers
    )

    assert second_claim.status_code == 409



def test_worker_can_complete_own_ticket(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )

    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    create_user = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": "completeworker",
            "password": "CompleteWorkerPassword123!",
            "role": "worker"
        }
    )

    assert create_user.status_code == 200

    worker_login = client.post(
        "/api/auth/login",
        json={
            "username": "completeworker",
            "password": "CompleteWorkerPassword123!"
        }
    )

    assert worker_login.status_code == 200

    worker_headers = {
        "Authorization": f"Bearer {worker_login.json()['access_token']}"
    }

    room_response = client.post(
        "/api/admin/rooms",
        headers=admin_headers,
        json={"name": "Complete Test Room"}
    )

    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    ticket_response = client.post(
        "/api/public/reports",
        data={
            "kind": "fault",
            "room_id": str(room_id),
            "title": "Completion test",
            "description": "Testing ticket completion"
        }
    )

    assert ticket_response.status_code == 200
    ticket_id = ticket_response.json()["ticket_id"]

    claim_response = client.post(
        f"/api/tickets/{ticket_id}/claim",
        headers=worker_headers
    )

    assert claim_response.status_code == 200

    complete_response = client.post(
        f"/api/tickets/{ticket_id}/complete",
        headers=worker_headers,
        json={
            "completion_description": "Repaired and tested successfully"
        }
    )

    assert complete_response.status_code == 200
    assert complete_response.json()["ok"] is True

    ticket_check = client.get(
        f"/api/tickets/{ticket_id}",
        headers=worker_headers
    )

    assert ticket_check.status_code == 200
    assert ticket_check.json()["status"] == "done"


def test_worker_cannot_complete_another_workers_ticket(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )
    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    worker_headers = []

    for username in ["ownerworker", "otherworker"]:
        create_user = client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": username,
                "password": "WorkerPassword123!",
                "role": "worker"
            }
        )
        assert create_user.status_code == 200

        login = client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": "WorkerPassword123!"
            }
        )
        assert login.status_code == 200

        worker_headers.append({
            "Authorization": f"Bearer {login.json()['access_token']}"
        })

    room_response = client.post(
        "/api/admin/rooms",
        headers=admin_headers,
        json={"name": "Ownership Test Room"}
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    ticket_response = client.post(
        "/api/public/reports",
        data={
            "kind": "fault",
            "room_id": str(room_id),
            "title": "Ownership test",
            "description": "Testing ticket ownership permissions"
        }
    )
    assert ticket_response.status_code == 200
    ticket_id = ticket_response.json()["ticket_id"]

    claim_response = client.post(
        f"/api/tickets/{ticket_id}/claim",
        headers=worker_headers[0]
    )
    assert claim_response.status_code == 200

    complete_response = client.post(
        f"/api/tickets/{ticket_id}/complete",
        headers=worker_headers[1],
        json={
            "completion_description": "Trying to complete another worker's ticket"
        }
    )
    assert complete_response.status_code == 403

    ticket_check = client.get(
        f"/api/tickets/{ticket_id}",
        headers=admin_headers
    )
    assert ticket_check.status_code == 200
    assert ticket_check.json()["status"] == "in_progress"
    assert ticket_check.json()["assigned_to"] == "ownerworker"


def test_admin_can_complete_workers_ticket(client):
    admin_login = client.post(
        "/api/auth/login",
        json={
            "username": "testadmin",
            "password": "TestAdminPassword123!"
        }
    )
    assert admin_login.status_code == 200

    admin_headers = {
        "Authorization": f"Bearer {admin_login.json()['access_token']}"
    }

    create_user = client.post(
        "/api/admin/users",
        headers=admin_headers,
        json={
            "username": "admincompleteworker",
            "password": "WorkerPassword123!",
            "role": "worker"
        }
    )
    assert create_user.status_code == 200

    worker_login = client.post(
        "/api/auth/login",
        json={
            "username": "admincompleteworker",
            "password": "WorkerPassword123!"
        }
    )
    assert worker_login.status_code == 200

    worker_headers = {
        "Authorization": f"Bearer {worker_login.json()['access_token']}"
    }

    room_response = client.post(
        "/api/admin/rooms",
        headers=admin_headers,
        json={"name": "Admin Completion Test Room"}
    )
    assert room_response.status_code == 200
    room_id = room_response.json()["id"]

    ticket_response = client.post(
        "/api/public/reports",
        data={
            "kind": "fault",
            "room_id": str(room_id),
            "title": "Admin completion test",
            "description": "Testing administrator completion permissions"
        }
    )
    assert ticket_response.status_code == 200
    ticket_id = ticket_response.json()["ticket_id"]

    claim_response = client.post(
        f"/api/tickets/{ticket_id}/claim",
        headers=worker_headers
    )
    assert claim_response.status_code == 200

    complete_response = client.post(
        f"/api/tickets/{ticket_id}/complete",
        headers=admin_headers,
        json={
            "completion_description": "Administrator completed the ticket"
        }
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["ok"] is True

    ticket_check = client.get(
        f"/api/tickets/{ticket_id}",
        headers=admin_headers
    )
    assert ticket_check.status_code == 200
    assert ticket_check.json()["status"] == "done"
    assert ticket_check.json()["assigned_to"] == "admincompleteworker"

