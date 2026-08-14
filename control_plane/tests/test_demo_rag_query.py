def test_rag_query_uses_trusted_session_and_ignores_claimed_user_id(
    client_as_a, rag_port
):
    response = client_as_a.post(
        "/api/retrieval/query",
        json_body={
            "question": "项目验收要求是什么？",
            "asset_id": "asset-acceptance",
            "user_id": "user-b",
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "验收要求一：交付文件需包含最终版本与验收清单。"
    assert response.json()["citations"][0]["asset_version_id"] == "version-acceptance-v1"
    assert len(rag_port.query_calls) == 1
    actor, question, asset_id = rag_port.query_calls[0]
    assert actor.actor_id == "user-a"
    assert question == "项目验收要求是什么？"
    assert asset_id == "asset-acceptance"
