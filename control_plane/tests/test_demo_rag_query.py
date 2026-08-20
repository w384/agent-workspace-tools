def test_rag_query_uses_trusted_session_and_ignores_claimed_user_id(
    client_as_a, rag_port
):
    response = client_as_a.post(
        "/api/retrieval/query",
        json_body={
            "question": "2024年度营业收入是多少？",
            "asset_id": "asset-acceptance",
            "user_id": "user-b",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "2024年度营业收入为4,860万元。"
    assert response.json()["citations"][0]["asset_version_id"] == "version-income-v1"
    assert len(rag_port.query_calls) == 1
    actor, question, asset_id = rag_port.query_calls[0]
    assert actor.actor_id == "user-a"
    assert question == "2024年度营业收入是多少？"
    assert asset_id == "asset-acceptance"
