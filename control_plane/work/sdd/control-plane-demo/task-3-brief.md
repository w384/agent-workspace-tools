# Task 3 Brief 鈥?Gate 2 鑷‘璁ゃ€佺浜屼汉瀹℃壒涓庢墽琛屽璁?
鍏堝畬鏁磋鍙?`control_plane/docs/implementation-plan.md` 鐨?Global Constraints/Task 3銆?Task 1/2 鎶ュ憡锛屼互鍙婃墽琛屾€昏礋璐ｄ簬 2026-08-13 缁欏嚭鐨?Gate 2 濂戠害瑁佸喅銆傛湰浠诲姟鍙疄鐜?`control_plane/**`锛涗笉寰椾慨鏀规枃浠舵墽琛屽櫒銆佸喕缁撴鏂囨垨璺ㄥ煙妯″潡銆?
## 鍥哄畾鐢ㄦ埛璺緞

1. BFF 浠庡彲淇?session 鏋勯€?actor锛屽拷鐣?query/body/header 涓殑 `user_id`銆佽鑹层€佽矾寰勩€佺増鏈拰鎸囩汗浼€犲€笺€?2. BFF 浠庢帶鍒堕潰鏉冨▉瀹炰綋瑙ｆ瀽婧愯矾寰勩€乤ctive AssetVersion 涓庢寚绾癸紝瀵规簮鍜岀洰鏍囨墽琛?ACL 瑁佸喅銆?3. 浠讳竴鏄惧紡鎷掔粷鎴栨湭鎺堟潈璺緞浣挎暣鎵逛负 `DENY`锛氳繑鍥?403锛涗笉璋冪敤鎵ц鍣紱涓嶅垱寤?Plan銆丆onfirmation銆丄pproval 鎴?ExecutionJob锛涘彧璁板綍涓嶅惈鏈巿鏉冩鏂?璺緞鐨勬嫆缁濆璁°€?4. 鎺堟潈鐨勫皯閲?`move_rename` 涓?`SELF_CONFIRM`锛欰 鑾峰緱褰卞搷棰勮锛屽彧鏈?A 鍙‘璁ゅ苟鎵ц锛汢 鏃犲緟鍔炪€?5. 棰勫畾涔夐珮椋庨櫓 `trash` 涓?`APPROVAL_REQUIRED`锛欰 鍏堢‘璁よ嚜宸辩殑鎰忓浘锛岄殢鍚庢墠鍒涘缓涓€涓?pending Approval锛涗粎涓嶅悓浜?A 涓斿叿鏈夋敞鍏ョ殑 opaque 瀹℃壒瑙掕壊 ID锛坒ixture 浣跨敤 `role-approver-demo`锛夌殑 B 鍙壒鍑?鎷掔粷锛涙壒鍑嗗悗鎵嶆墽琛屻€?6. BFF 璋冪敤鎵ц鍣ㄦ椂浼犲彲淇?actor銆丄CL snapshot/decision銆乸lan hash銆佺増鏈?鎸囩汗涓庡箓绛夐敭锛涙墽琛屽櫒浠嶄繚鐣欐渶缁堥噸楠屻€傚唴閮ㄤ竴娆℃€у嚟璇佸彧鍦ㄩ€傞厤璋冪敤鏍堜腑涓存椂鎸佹湁骞剁珛鍗虫秷璐癸紝涓嶈繘鍏ュ疄浣撱€佹祻瑙堝櫒銆丏ify銆佸搷搴旀垨瀹¤銆?
## Canonical plan hash

瀹炵幇绾煙鍑芥暟/鍊煎璞°€傝緭鍏ヤ娇鐢ㄥ甫 `contract_version` 鐨?canonical JSON锛歎TF-8銆侀敭鎺掑簭銆佸浐瀹氱揣鍑戝垎闅旂锛涜嚦灏戠粦瀹氾細

- `contract_version`
- `plan_id`
- `workspace_id`
- `actor_id`
- `decision_state`
- `decision_id`
- `policy_version`
- `context_version`
- `normalized_operations`
- 鎸?`asset_id` 绋冲畾鎺掑簭鐨?`asset_snapshots`锛屾瘡椤瑰惈 `asset_id/asset_version_id/content_fingerprint`
- `expires_at`锛圲TC ISO 8601锛?
`idempotency_key` 涓嶈繘鍏?plan hash銆傝緭鍏ラ『搴忓彉鍖栦絾璇箟鐩稿悓蹇呴』浜х敓鍚屼竴 hash锛涗换浣曠粦瀹氬瓧娈靛彉鍖栧繀椤绘敼鍙?hash銆傛瘮杈?expected/actual hash 鏃朵娇鐢ㄥ父閲忔椂闂存瘮杈冦€?
## 棰嗗煙涓庝粨鍌?
鏈€灏忚ˉ榻愶細

- `Plan` 淇濆瓨 workspace/creator銆佸洓鎬併€佺姸鎬併€乷perations銆乤sset snapshots銆乸lan hash銆乨ecision/policy/context version銆丄CL snapshot銆乪xpires/created time銆?- `Confirmation` 鍙厑璁歌鍒掑垱寤鸿€呮寜 expected hash 纭鎴栧彇娑堜竴娆°€?- `Approval` 浠呭湪楂橀闄╄鍒掔敱 A 纭鍚庡垱寤轰竴娆★紱瀹℃壒浜哄繀椤绘槸闈炲彂璧蜂汉鐨勫悎鏍?actor銆?- `ExecutionJob` 鐘舵€佸浐瀹氫负 `queued|running|completed|failed|rolled_back`锛涘箓绛夊敮涓€璇箟涓?`(plan_id, plan_hash, idempotency_key)`銆?- DDL 涓庨鍩熷悓姝ワ細涓嶅緱浣跨敤 `succeeded`锛屼笉寰楁妸 `idempotency_key` 璁句负鍏ㄥ眬鍞竴銆?- 浠撳偍鎿嶄綔鍦ㄥ唴瀛樺疄鐜颁腑鎸?expected state/hash 鍋氬師瀛愬紡妫€鏌ワ紱鐪熷疄 PostgreSQL 杩佺Щ浠嶅彧鍋氶潤鎬?schema 楠岃瘉锛屼笉瀹夎鏁版嵁搴撱€?
寤鸿鐘舵€佹満锛?
```text
SELF_CONFIRM:
pending_confirmation -> executing -> completed|failed

APPROVAL_REQUIRED:
pending_confirmation -> pending_approval
pending_approval -> approved -> executing -> completed|failed
pending_approval -> rejected
```

## 绔彛涓?API

鎵╁睍 `FileExecutorPort` 濂戠害妗╋細

```python
create_plan(actor, resolved_operations, asset_snapshots, acl_snapshot,
            policy_version, expires_at, idempotency_key) -> FilePlanPreview

confirm_and_execute(actor, plan_id, expected_plan_hash, asset_snapshots,
                    acl_snapshot, decision, confirmation_evidence,
                    approval_evidence, idempotency_key) -> ExecutionResult
```

`FilePlanPreview` 鑷冲皯鍖呭惈 `plan_id/plan_hash/decision/normalized_operations/impact_summary/audit_event_id`锛?`ExecutionResult` 鑷冲皯鍖呭惈 `execution_job_id/status/operation_id/audit_event_id/failure_code?`銆備换浣曡緭鍏ヨ緭鍑哄潎鏃?token/credential/secret 瀛楁銆?
澶栭儴 BFF锛?
- `POST /api/plans`
- `POST /api/plans/{plan_id}/confirm`
- `GET /api/approvals/pending`
- `POST /api/approvals/{approval_id}/decide`

纭/瀹℃壒璇锋眰鎼哄甫 `expected_plan_hash` 鍜?`Idempotency-Key`锛涘彲淇?actor/role 鍙潵鑷?session銆?
## RED 娴嬭瘯鏈€灏忕煩闃?
`test_gate2_plans.py`锛?
- 鎺堟潈绉诲姩杩斿洖瀹夊叏棰勮鍜?`SELF_CONFIRM`锛屾湭纭涓嶆墽琛岋紝B 鏃犲緟鍔炪€?- A session 涓吉閫?B 鐨?user/role/source/version/fingerprint 涓嶈兘鏀瑰彉鏉冨▉杈撳叆銆?- 婧愭垨鐩爣浠讳竴 DENY銆佹贩鍚堟壒娆″惈 DENY锛屾暣鎵归浂涓嬫父/闆舵寔涔呭寲銆?- 浠呭垱寤鸿€呭彲纭 SELF_CONFIRM锛沨ash/expiry/context/policy/active version 婕傜Щ fail closed銆?- 鍚屼竴 `(plan_id, plan_hash, idempotency_key)` 閲嶈瘯鍙墽琛屼竴娆°€佽繑鍥炲悓涓€ job銆?- canonical hash 瀵归敭椤哄簭涓?asset 杈撳叆椤哄簭绋冲畾锛屽姣忎釜缁戝畾瀛楁鏁忔劅銆?- 鍝嶅簲銆佸疄浣撱€佸璁°€佹墽琛屽櫒璁板綍鍧囦笉鍚?bearer/key/credential/涓婁紶姝ｆ枃鎴栨湭鎺堟潈璺緞銆?
`test_approval.py`锛?
- 楂橀闄╁垱寤哄悗灏氭棤 Approval锛汚 纭鍚庢墠鏈変竴涓?pending銆?- 鍏锋湁 `role-approver-demo` 涓斾笉鏄?A 鐨?B 鍙壒鍑嗭紝闅忓悗鍙墽琛屼竴娆°€?- A 鍗充究鏈夊鎵硅鑹蹭篃涓嶈兘鑷壒锛涙棤閰嶇疆瑙掕壊鑰呬笉鑳藉喅瀹氾紱瀹㈡埛绔吉閫犺鑹叉棤鏁堛€?- 鎷掔粷涓虹粓鎬佷笖浠庝笉鎵ц锛汼ELF_CONFIRM/DENY 鍧囦笉寰楀垱寤哄鎵广€?- hash/expiry/state 婕傜Щ鏃跺鎵?fail closed銆?
## TDD 涓庨獙璇?
鍏堝啓娴嬭瘯骞跺疄闄呰幏寰?RED锛屽啀鍐欐渶灏?GREEN锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate2_plans.py control_plane\tests\test_approval.py -q -p no:cacheprovider
```

瀹屾垚鍚庡璺戝叏閮?`control_plane/tests`锛屾墽琛?`git diff --check -- control_plane`锛屽苟鎶?RED/GREEN 鍘熷鎽樿銆佹枃浠舵竻鍗曘€佽嚜瀹°€佺湡瀹?PostgreSQL 鏈獙璇侀闄╁啓鍏?`task-3-report.md`銆?
