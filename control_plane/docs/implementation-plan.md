# 涓彴鎺у埗闈㈡渶灏?DEMO 瀹炴柦璁″垝

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 鍦ㄧ粺涓€ Web/BFF 鍏ュ彛璇佹槑鍚屼竴 `Asset/AssetVersion` 鍙寜鍚屼竴 ACL 瀹屾垚涓婁紶銆佷綆椋庨櫓鑷‘璁ゆ暣鐞嗗拰鐭ヨ瘑鏌ヨ锛屽苟璁╄秺鏉冩煡璇㈠湪璋冪敤 RAG 鍓嶅け璐ャ€?
**Architecture:** `control_plane` 鏄祻瑙堝櫒鍞竴鍏ュ彛锛屼互鏈嶅姟绔?session 寤虹珛 `TrustedActorContext`锛屽湪 PostgreSQL 棰嗗煙妯″瀷涓婂仛鍥涙€佽鍐筹紱鏂囦欢鎵ц鍣ㄣ€丏ify 鍜?RAG 鍙€氳繃娉ㄥ叆绔彛璋冪敤銆傛祴璇曚娇鐢ㄥ唴瀛樹粨鍌ㄤ笌褰曞埗鍨嬪绾︽々锛岀敓浜ф暟鎹粨鏋勭敱 PostgreSQL DDL 鍥哄畾锛涙湰鍒囩墖涓嶅畨瑁?PostgreSQL銆丏ify 鎴?RAG銆?
**Tech Stack:** Python 3.12銆丗astAPI銆丳ydantic銆乸ytest銆丳ostgreSQL DDL銆佸師鐢?HTML/CSS/JavaScript銆?
## Global Constraints

- 鍐荤粨绾茶 v1 涓嶅彉锛涙柊澧炴兂娉曞彧杩涘叆 LATER锛屼笉鎵╁ぇ鏋舵瀯鎴栨紨绀烘晠浜嬨€?- 娴忚鍣ㄥ彧璁块棶 BFF锛涗笉寰楃洿杈炬枃浠舵墽琛屽櫒銆丏ify 鎴?RAG銆?- 瀹㈡埛绔?body銆乹uery 鎴?header 涓殑 `user_id` 姘歌繙涓嶆槸鍙俊韬唤锛涘彧浣跨敤鏈嶅姟绔?session 瑙ｆ瀽鍑虹殑 actor銆?- 鏉冮檺/椋庨櫓鍥涙€佸浐瀹氫负 `DIRECT / SELF_CONFIRM / APPROVAL_REQUIRED / DENY`锛屼紭鍏堢骇涓?`DENY > APPROVAL_REQUIRED > SELF_CONFIRM > DIRECT`銆?- 鎺堟潈鐩綍鍐呬笖涓嶈鐩栫殑涓婁紶涓?`DIRECT`锛涙墽琛屽櫒杩斿洖鐨?`content_fingerprint=sha256:<digest>` 鏄?`AssetVersion` 鎸囩汗杈撳叆锛孊FF 涓嶉噸鏂拌绠楁枃浠跺唴瀹瑰搱甯屻€?- 鎺堟潈鑼冨洿鍐呯殑灏戦噺 `move_rename` 涓?`SELF_CONFIRM`锛涘彂璧蜂汉鏈汉纭锛岀鐞嗗憳 B 涓嶄粙鍏ャ€?- 浠呴瀹氫箟楂橀闄?`trash` 涓?`APPROVAL_REQUIRED`锛涘鎵逛汉蹇呴』鏈夐厤缃敞鍏ョ殑 opaque 瀹℃壒瑙掕壊 ID锛坉emo fixture 浣跨敤 `role-approver-demo`锛変笖涓嶅緱鏄彂璧蜂汉銆?- 鏄庣‘ ACL 鎷掔粷涓?`DENY`锛屼笉寰楀垱寤?Plan銆丆onfirmation 鎴?Approval锛屼篃涓嶅緱璋冪敤鎵ц鍣?RAG/LLM銆?- RAG 琚皟鐢ㄥ墠 BFF 蹇呴』鍏堟巿鏉冿紱RAG 浠嶄繚鐣欒嚜韬?ACL 鍓嶇疆闃茬嚎銆傝秺鏉冨搷搴斿浐瀹氬寘鍚?`retrieved_count=0`銆乣llm_invoked=false`銆佺┖ citations銆?- `Asset`銆乣AssetVersion`銆乣PermissionGrant` 鐨勬潈濞佹暟鎹粨鏋勪负 PostgreSQL锛涙枃浠舵鏂囧拰 Qdrant chunk 閮戒笉鏄浜屼唤鏂囦欢鏉冨▉銆?- 浠呬慨鏀?`control_plane/**`锛涗笉瀹夎/鍙戝竷澶栭儴绯荤粺銆佷笉鎺ㄩ€佽繙绔€佷笉璁块棶鎴栦慨鏀圭湡瀹炲叕鍏辩洏銆?
---

### Task 1: 棰嗗煙妯″瀷銆佸洓鎬佺瓥鐣ヤ笌 PostgreSQL Schema

**Files:**
- Create: `control_plane/__init__.py`
- Create: `control_plane/app/__init__.py`
- Create: `control_plane/app/domain.py`
- Create: `control_plane/app/policy.py`
- Create: `control_plane/app/repository.py`
- Create: `control_plane/migrations/001_control_plane.sql`
- Test: `control_plane/tests/test_policy.py`
- Test: `control_plane/tests/test_schema.py`

**Interfaces:**
- Produces: `TrustedActorContext`, `PermissionGrant`, `AuthorizationDecision`, `Asset`, `AssetVersion`, `Plan`, `Confirmation`, `Approval`, `ExecutionJob`, `AuditEvent`, `ChunkMetadata`.
- Produces: `evaluate_authorization(actor, grants, action, paths, overwrite=False) -> AuthorizationDecision`.
- Produces: `ControlPlaneRepository` protocol and `InMemoryControlPlaneRepository` used by later tasks.

- [ ] **Step 1: Write failing policy tests**

```python
def test_explicit_deny_wins_before_high_risk_escalation():
    decision = evaluate_authorization(
        actor=actor_a,
        grants=[allow_organized, deny_restricted],
        action=Action.TRASH,
        paths=("organized/restricted/payroll.pdf",),
    )
    assert decision.state is DecisionState.DENY

def test_low_risk_upload_is_direct_and_move_is_self_confirm():
    assert upload_decision.state is DecisionState.DIRECT
    assert move_decision.state is DecisionState.SELF_CONFIRM
```

- [ ] **Step 2: Run RED**

Run: `python -B -m pytest control_plane/tests/test_policy.py control_plane/tests/test_schema.py -q -p no:cacheprovider`

Expected: collection/import failure because the domain and schema do not exist.

- [ ] **Step 3: Implement the minimum domain, policy, repository and DDL**

Policy rules are exact: invalid/unauthorized path or explicit deny -> `DENY`; authorized `trash` -> `APPROVAL_REQUIRED`; authorized `move_rename`/`create_folder` -> `SELF_CONFIRM`; authorized non-overwrite `upload` and authorized `query` -> `DIRECT`; overwrite upload -> `DENY`.

- [ ] **Step 4: Run GREEN**

Run the Step 2 command; expected all tests pass.

### Task 2: 鍙俊 session銆丟ate 1 涓婁紶涓庣姸鎬佸洖鍐?
**Files:**
- Create: `control_plane/app/sessions.py`
- Create: `control_plane/app/ports.py`
- Create: `control_plane/app/service.py`
- Create: `control_plane/app/main.py`
- Test: `control_plane/tests/conftest.py`
- Test: `control_plane/tests/test_gate1_upload.py`
- Test: `control_plane/tests/test_session_boundary.py`

**Interfaces:**
- Consumes: Task 1 domain/repository/policy.
- Produces: HttpOnly `cp_session` bearer cookie resolved to `TrustedActorContext`.
- Produces: `FileExecutorPort.upload(...) -> UploadResult(path, name, size_bytes, content_fingerprint)`.
- Produces: `RagPort.enqueue_version(asset_version)`, and internal index-state callback.

- [ ] **Step 1: Write failing API tests**

```python
def test_forged_user_id_is_ignored(client_as_a):
    response = client_as_a.get("/api/session/me", params={"user_id": "user-b"})
    assert response.json()["actor_id"] == "user-a"

def test_upload_uses_executor_fingerprint_without_rehashing(client_as_a, file_executor):
    response = client_as_a.post(
        "/api/uploads?user_id=user-b",
        data={"directory": "organized"},
        files={"file": ("report.txt", b"payload", "text/plain")},
    )
    assert response.json()["asset_version"]["content_fingerprint"] == "sha256:executor-digest"
```

- [ ] **Step 2: Run RED**

Run: `python -B -m pytest control_plane/tests/test_session_boundary.py control_plane/tests/test_gate1_upload.py -q -p no:cacheprovider`

Expected: imports/routes missing.

- [ ] **Step 3: Implement the minimum session and upload flow**

Session tokens are random bearer values stored only as SHA-256 digests server-side. Demo login verifies injected credentials with `hmac.compare_digest`, sets `HttpOnly; SameSite=Strict`, and all protected routes obtain actor only from the cookie. Upload first evaluates `DIRECT`, calls the executor once, then creates/reuses `Asset`, creates queued `AssetVersion` from executor `content_fingerprint`, enqueues RAG, and emits correlated audit events. Internal index callback requires `X-Internal-Service-Key` and permits `queued -> parsing -> indexed -> ready` or non-ready -> `failed`; failed v2 never replaces ready v1.

- [ ] **Step 4: Run GREEN**

Run the Step 2 command; expected all tests pass.

### Task 3: Gate 2 鑷‘璁ゃ€佺浜屼汉瀹℃壒涓庡璁″叧鑱?
**Files:**
- Modify: `control_plane/app/domain.py`
- Modify: `control_plane/app/repository.py`
- Modify: `control_plane/app/service.py`
- Modify: `control_plane/app/main.py`
- Test: `control_plane/tests/test_gate2_plans.py`
- Test: `control_plane/tests/test_approval.py`

**Interfaces:**
- Consumes: `FileExecutorPort.create_plan(...) -> FilePlanPreview` and `confirm_and_execute(...) -> ExecutionResult`.
- Produces: `POST /api/plans`, `POST /api/plans/{plan_id}/confirm`, `GET /api/approvals/pending`, `POST /api/approvals/{approval_id}/decide`.

- [ ] **Step 1: Write failing Gate 2 tests**

```python
def test_a_self_confirms_low_risk_move_without_b_approval(client_as_a, repo):
    created = client_as_a.post("/api/plans", json={"operations": [move_operation]}).json()
    assert created["decision"] == "SELF_CONFIRM"
    assert repo.list_pending_approvals("user-b") == []
    confirmed = client_as_a.post(f"/api/plans/{created['plan_id']}/confirm", json={"user_id": "user-b"})
    assert confirmed.status_code == 202

def test_deny_creates_no_plan_or_approval(client_as_a, repo, file_executor):
    response = client_as_a.post("/api/plans", json={"operations": [restricted_move]})
    assert response.status_code == 403
    assert repo.plans == {}
    assert repo.approvals == {}
    assert file_executor.plan_calls == []
```

- [ ] **Step 2: Run RED**

Run: `python -B -m pytest control_plane/tests/test_gate2_plans.py control_plane/tests/test_approval.py -q -p no:cacheprovider`

- [ ] **Step 3: Implement exact state transitions**

`SELF_CONFIRM` plans may be confirmed only by the creator's trusted session. `APPROVAL_REQUIRED` creates one pending Approval; only a different actor with the configured opaque approver role ID may approve/reject. `DENY` returns before calling executor or persisting a plan. Execution request includes actor context, `plan_hash`, asset/version fingerprints, ACL snapshot and idempotency key; the BFF never returns the executor's one-time credential. Every transition appends an `AuditEvent` sharing request/run/plan/job IDs.

- [ ] **Step 4: Run GREEN**

Run the Step 2 command; expected all tests pass.

### Task 4: 鍚屼竴瀵硅瘽鍏ュ彛銆丷AG 鍓嶇疆鎷掔粷涓庢渶灏?UI

**Files:**
- Modify: `control_plane/app/ports.py`
- Modify: `control_plane/app/service.py`
- Modify: `control_plane/app/main.py`
- Create: `control_plane/static/index.html`
- Create: `control_plane/static/app.js`
- Create: `control_plane/static/styles.css`
- Create: `control_plane/README.md`
- Test: `control_plane/tests/test_conversation.py`
- Test: `control_plane/tests/test_ui.py`

**Interfaces:**
- Consumes: `DifyPort.route(message) -> RoutedIntent` and `RagPort.query(actor, query, asset_ids, decision_id) -> RetrievalResult`.
- Produces: `POST /api/conversations/{conversation_id}/messages` for both `organize` and `query` intents.

- [ ] **Step 1: Write failing conversation/UI tests**

```python
def test_denied_query_stops_before_rag_and_llm(client_as_a, rag):
    response = client_as_a.post(
        "/api/conversations/demo/messages",
        json={"message": "鏌ヨ宸ヨ祫", "intent": "query", "asset_ids": [restricted_asset_id]},
    )
    assert response.status_code == 403
    assert response.json()["error"]["evidence"] == {
        "retrieved_count": 0,
        "llm_invoked": False,
        "citations": [],
    }
    assert rag.query_calls == []
```

- [ ] **Step 2: Run RED**

Run: `python -B -m pytest control_plane/tests/test_conversation.py control_plane/tests/test_ui.py -q -p no:cacheprovider`

- [ ] **Step 3: Implement one chat route and minimal UI**

The same route accepts optional explicit demo intent; absent intent is resolved only through injected Dify port. Organize delegates to Task 3 planning; query authorizes every requested active AssetVersion before one RAG call. UI talks only to BFF routes and renders upload parse/index state, plan preview/confirm, approval-required, denial evidence, answer citations and correlated audit IDs.

- [ ] **Step 4: Run GREEN and full verification**

Run:

```powershell
python -B -m pytest control_plane/tests -q -p no:cacheprovider
git diff --check -- control_plane
```

Expected: all control-plane tests pass and diff check exits 0.

