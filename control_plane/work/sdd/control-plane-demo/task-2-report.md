# Task 2 瀹炴柦鎶ュ憡 - 鍙俊 session銆丟ate 1 涓婁紶涓庣姸鎬佸洖鍐?
## 缁撹

鐘舵€侊細`DONE_WITH_CONCERNS`銆?
Task 2 宸叉寜鏈€鏂?Gate1 瑁佸喅瀹屾垚骞堕€氳繃 scoped 鍏ㄩ噺楠岃瘉銆傚綋鍓嶅疄鐜拌鐩栵細鍙俊 session 杈圭晫銆佹湇鍔＄ request/run 鍏宠仈銆丏IRECT 涓婁紶銆佸凡鐭ュ悓璺緞 Asset 鐩存帴 DENY銆佹墽琛屽櫒鐩爣鍐茬獊缁撴瀯鍖?409銆丷AG enqueue 澶辫触鍚?queued AssetVersion 杞?failed銆乧allback 閫氳繃鎸佷箙瀹¤鎭㈠鍏宠仈銆佺粺涓€ `{error:{code,message}}` 閿欒 envelope锛屼互鍙婃晱鎰熶俊鎭笉杩涘叆瀹¤銆?
娈嬩綑 concern 涓昏鏄紨绀虹骇鍐呭瓨浠撳偍灏氭湭钀界湡瀹?PostgreSQL 瀹炵幇銆丷AG enqueue 澶辫触鍚庢病鏈?outbox/retry/recovery 闂幆銆佺湡瀹炴墽琛屽櫒/RAG/鍏叡鐩橀泦鎴愭湭楠岃瘉銆?
## 鑼冨洿

- 鍙慨鏀?`control_plane/**`銆?- 鏈慨鏀?`service/**`銆乣plugin/**`銆佹牴鏂囨。銆佸喕缁?brief 姝ｆ枃鎴栧閮ㄧ郴缁熴€?- 鏈畨瑁呬緷璧栥€佹湭鎻愪氦銆佹湭鎺ㄩ€併€佹湭璁块棶鐪熷疄鍏叡鐩樸€?- 娴嬭瘯浣跨敤鍐呭瓨 repository銆佸唴瀛?ASGI 瀹㈡埛绔拰褰曞埗绔彛锛涗笉杩炴帴鐪熷疄 PostgreSQL銆佹枃浠舵墽琛屽櫒鎴?RAG銆?
## 鍙樻洿鏂囦欢

鐢熶骇浠ｇ爜锛?
- `control_plane/app/domain.py`锛歚TrustedActorContext` 澧炲姞骞跺己鍒堕潪绌?`session_id/request_id/run_id/role_ids`锛沗AuditEvent` 澧炲姞 `run_id`锛涘垹闄?`roles` 鍙屽瓨鍌ㄥ吋瀹广€?- `control_plane/app/policy.py`锛氭巿鏉冨垽鏂粺涓€浣跨敤 `role_ids`銆?- `control_plane/app/repository.py`锛氬鍔?`find_asset_by_path` 涓?`find_asset_version_creation_event`锛涘唴瀛樹粨鍌ㄦ寜瀹¤浜嬩欢鎭㈠ callback correlation銆?- `control_plane/app/sessions.py`锛氭湇鍔＄ session store銆乧ookie digest 瀛樺偍銆佸彲淇?actor 鎭㈠涓庢瘡璇锋眰 request_id 鐢熸垚銆?- `control_plane/app/ports.py`锛氭枃浠舵墽琛屽櫒涓?RAG 绔彛锛宍UploadResult` 鏍￠獙 executor 鎸囩汗鏍煎紡銆?- `control_plane/app/service.py`锛欸ate1 涓婁紶缂栨帓銆丄CL DENY 鑴辨晱瀹¤銆佸悓璺緞宸茬煡 Asset DENY銆佹墽琛屽櫒鍐茬獊/寮傚父鏄犲皠銆丷AG enqueue 澶辫触缃?failed銆乧allback 鍏宠仈鎭㈠銆?- `control_plane/app/main.py`锛氱櫥褰?鐧诲嚭/session/upload/internal callback 璺敱锛涚粺涓€涓氬姟閿欒銆乿alidation 閿欒涓庣鍙ｅ紓甯?envelope銆?
娴嬭瘯涓庢姤鍛婏細

- `control_plane/tests/conftest.py`锛氭渶灏?ASGI 娴嬭瘯瀹㈡埛绔€乻ession fixture銆佸綍鍒?executor/RAG 绔彛涓庡紓甯告敞鍏ャ€?- `control_plane/tests/test_policy.py`锛歍ask1 policy/schema 鍥炲綊涓庡彲淇?actor 蹇呭～瀛楁 RED/GREEN銆?- `control_plane/tests/test_session_boundary.py`锛氬彲淇?cookie銆佸鎴风 user_id/request_id 蹇界暐銆乻ession/logout/internal key 杈圭晫銆?- `control_plane/tests/test_gate1_upload.py`锛欴IRECT 涓婁紶銆丏ENY 闆跺壇浣滅敤銆佸悓璺緞 DENY銆佹墽琛屽櫒鍐茬獊銆乪xecutor/RAG 寮傚父銆佸璁¤劚鏁忋€乧allback correlation銆丷EADY 涓嶉殣寮忔縺娲汇€乫ailed v2 淇濈暀 active v1銆?- `control_plane/work/sdd/control-plane-demo/task-2-report.md`锛氭湰鎶ュ憡銆?
## RED/GREEN 璇佹嵁

鍒濆 Task2 RED锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_session_boundary.py control_plane\tests\test_gate1_upload.py -q -p no:cacheprovider
```

缁撴灉锛氶€€鍑虹爜 `1`锛沗ModuleNotFoundError: No module named 'control_plane.app.main'`銆?
鍒濆 Task2 GREEN锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_policy.py control_plane\tests\test_schema.py control_plane\tests\test_session_boundary.py control_plane\tests\test_gate1_upload.py -q -p no:cacheprovider
```

缁撴灉锛歚34 passed in 0.20s`锛涚嫭绔嬪璺戞浘寰楀埌 `34 passed in 0.16s`銆?
Fix A RED - ACL DENY 蹇呴』鍐欒劚鏁忓璁★細

```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate1_upload.py::test_denied_upload_has_no_executor_rag_asset_or_version_side_effect control_plane\tests\test_gate1_upload.py::test_denied_upload_audit_never_retains_the_unauthorized_full_path -q -p no:cacheprovider
```

缁撴灉锛氶€€鍑虹爜 `1`锛沗2 failed in 0.11s`锛涘け璐ョ偣涓?DENY 瀹¤浜嬩欢涓嶅瓨鍦ㄣ€?
Fix A GREEN锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate1_upload.py::test_denied_upload_has_no_executor_rag_asset_or_version_side_effect control_plane\tests\test_gate1_upload.py::test_denied_upload_audit_never_retains_the_unauthorized_full_path -q -p no:cacheprovider
```

缁撴灉锛歚2 passed in 0.07s`銆?
Fix B RED - 閲嶅缓 service 鍚?callback 浠嶆仮澶?request/run/actor锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate1_upload.py::test_rebuilt_service_restores_callback_request_run_and_actor_from_persisted_audit -q -p no:cacheprovider
```

缁撴灉锛氶€€鍑虹爜 `1`锛沗1 failed in 0.10s`锛涘け璐ョ偣涓?repository 缂哄皯鎸佷箙瀹¤鏌ヨ鎺ュ彛銆?
Fix B GREEN锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate1_upload.py::test_rebuilt_service_restores_callback_request_run_and_actor_from_persisted_audit control_plane\tests\test_gate1_upload.py::test_index_chain_records_correlated_audit_without_implicit_activation_and_failed_v2_keeps_v1 -q -p no:cacheprovider
```

缁撴灉锛歚2 passed in 0.07s`銆?
Fix C RED - `TrustedActorContext` 蹇呭～鍏宠仈瀛楁锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_policy.py::test_trusted_actor_context_rejects_empty_trusted_correlation_fields -q -p no:cacheprovider
```

缁撴灉锛氶€€鍑虹爜 `1`锛沗4 failed in 0.07s`锛涚┖ `session_id/request_id/run_id/role_ids` 鏈嫆缁濄€?
Fix C GREEN 涓?Task1 鍥炲綊锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_policy.py control_plane\tests\test_session_boundary.py -q -p no:cacheprovider
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_policy.py control_plane\tests\test_schema.py -q -p no:cacheprovider
```

缁撴灉锛氬垎鍒负 `24 passed in 0.09s`銆乣23 passed in 0.04s`銆?
Fix D RED - validation/executor/RAG 缁撴瀯鍖栭敊璇笌澶辫触瀹¤锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_session_boundary.py::test_request_validation_errors_use_unified_error_envelope control_plane\tests\test_gate1_upload.py::test_executor_exception_returns_safe_error_and_appends_sanitized_failure_audit control_plane\tests\test_gate1_upload.py::test_rag_exception_fails_queued_version_and_returns_safe_correlated_error -q -p no:cacheprovider
```

缁撴灉锛氶€€鍑虹爜 `1`锛沗3 failed in 0.13s`锛泇alidation 浠嶄负 FastAPI 榛樿 `detail`锛宔xecutor/RAG 寮傚父浠嶈繑鍥炴鏋?500銆?
Fix D GREEN锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_session_boundary.py::test_request_validation_errors_use_unified_error_envelope control_plane\tests\test_gate1_upload.py::test_executor_exception_returns_safe_error_and_appends_sanitized_failure_audit control_plane\tests\test_gate1_upload.py::test_rag_exception_fails_queued_version_and_returns_safe_correlated_error -q -p no:cacheprovider
```

缁撴灉锛歚3 passed in 0.08s`銆?
Fix E/Gate1 RED - 宸茬煡鍚岃矾寰?DENY 涓庢墽琛屽櫒鐩爣鍐茬獊 409锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate1_upload.py::test_known_asset_path_is_denied_before_executor_without_a_new_version control_plane\tests\test_gate1_upload.py::test_executor_target_conflict_maps_to_stable_conflict_without_asset_version -q -p no:cacheprovider
```

缁撴灉锛氶€€鍑虹爜 `1`锛沗2 failed in 0.12s`锛涘凡鐭ュ悓璺緞浠嶈蛋鎴愬姛涓婁紶锛屾墽琛屽櫒 `FileExistsError` 浠嶆槧灏勪负閫氱敤 502銆?
Fix E/Gate1 GREEN锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate1_upload.py::test_known_asset_path_is_denied_before_executor_without_a_new_version control_plane\tests\test_gate1_upload.py::test_executor_target_conflict_maps_to_stable_conflict_without_asset_version -q -p no:cacheprovider
```

缁撴灉锛歚2 passed in 0.07s`銆?
Fix E 鍥炲綊璋冩暣 - 涓嶅啀鐢ㄩ噸澶嶄笂浼犳瀯閫?v2锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_gate1_upload.py::test_index_chain_records_correlated_audit_without_implicit_activation_and_failed_v2_keeps_v1 -q -p no:cacheprovider
```

缁撴灉锛歚1 passed in 0.06s`銆?
## 鏈€缁堥獙璇?
scoped 鍏ㄩ噺锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_policy.py control_plane\tests\test_schema.py control_plane\tests\test_session_boundary.py control_plane\tests\test_gate1_upload.py -q -p no:cacheprovider
```

缁撴灉锛?
```text
............................................                             [100%]
44 passed in 0.21s
```

diff check锛?
```powershell
git diff --check -- control_plane
```

缁撴灉锛氶€€鍑虹爜 `0`锛屾棤杈撳嚭銆傝鏄庯細褰撳墠 `control_plane/` 鍦?Git 涓粛鏄剧ず涓烘湭璺熻釜鐩綍锛屾墍浠ヤ笂杩板懡浠ゆ寜鐢ㄦ埛鎸囧畾鎵ц骞堕€氳繃锛屼絾鏅€?tracked diff 鏃犳硶灞曞紑鏂版枃浠跺唴閮ㄥ樊寮傦紱鏈敼鍔?Git index銆?
鑼冨洿鏍稿锛?
```powershell
git status --short -- control_plane
```

缁撴灉锛歚?? control_plane/`銆傛湰杞疄闄呭垱寤?淇敼鏂囦欢鍧囦綅浜?`control_plane/**`銆?
## 鑷

- `TrustedActorContext` 鐨?`session_id/request_id/run_id/role_ids` 鐜板湪涓洪潪绌哄繀濉紱鍙椾繚鎶よ矾鐢变粛瀹屽叏蹇界暐 query/body/header 涓鎴风浼€犵殑 `user_id` 涓?request id銆?- `ControlPlaneService` 涓嶅啀淇濆瓨 `_request_ids_by_version` 杩涚▼鍐呮槧灏勶紱callback 閫氳繃 repository 鏌ヨ `asset_version_created` 瀹¤鎭㈠鍘?actor/request/run銆?- READY callback 鍙浆鐘舵€佷笌鍐欏璁★紝涓嶈皟鐢?`activate_asset_version`锛涙樉寮?activation 浠嶆槸鐙珛 repository 鎿嶄綔銆?- ACL DENY 鍐?`upload_denied`锛屽彧鍚?action/decision/reason 涓?request/run 鍏宠仈锛沞xecutor/RAG/Asset/AssetVersion 闆跺壇浣滅敤銆?- 宸茬煡 Asset/current_path 鍚岃矾寰勪笂浼犲湪 BFF 灞傜洿鎺?DENY锛涙湭鐭ヤ絾鎵ц鍣ㄥ彂鐜板叕鍏辩洏鐩爣鍐茬獊鏃惰繑鍥炵粨鏋勫寲 409锛屼笉鍒涘缓鎴愬姛 AssetVersion銆?- executor 寮傚父鍜?RAG enqueue 寮傚父鍧囪繑鍥炲浐瀹氱粨鏋勫寲閿欒锛屼笉娉勯湶寮傚父姝ｆ枃銆乧ookie bearer銆乮nternal key銆乸assword銆佷笂浼犳鏂囨垨鏈巿鏉冨畬鏁磋矾寰勩€?- RAG enqueue 鍦?queued version 鍒涘缓鍚庡け璐ユ椂锛屽皢璇?version 杞?`failed`锛宍failure_code=index_enqueue_failed`锛屽苟淇濈暀鏃犻殣寮忔縺娲昏涓恒€?- 褰撳墠娌℃湁瀹炵幇 Task3/4銆乷utbox銆乺etry銆乺ecovery endpoint 鎴栫湡瀹炲叕鍏辩洏璁块棶銆?
## 娈嬩綑椋庨櫓

1. PostgreSQL repository銆佽縼绉绘墽琛屽拰璺ㄨ繘绋嬬湡瀹炴寔涔呭寲灏氭湭瀹炵幇锛涙湰杞彧鐢?InMemory repository 楠岃瘉濂戠害褰㈢姸銆?2. RAG enqueue 澶辫触鍚庡彧杩涘叆 `failed` 骞跺啓瀹¤锛屽皻鏃?outbox/retry/recovery 闂幆锛涜繖鏄?LATER 椤广€?3. 鐪熷疄鏂囦欢鎵ц鍣ㄣ€佺湡瀹?RAG銆乵ultipart 澶ф枃浠躲€佽秴鏃躲€佸苟鍙戠珵鎬佸拰鍏叡鐩樻渶缁堝啿绐佸彧閫氳繃绔彛寮傚父妯℃嫙锛屾湭鍋氱鍒扮楠岃瘉銆?4. BFF 宸茬煡鍚岃矾寰勬鏌ュ拰鎵ц鍣?create-only 鍐茬獊涔嬮棿浠嶅彲鑳藉瓨鍦ㄥ苟鍙戠獥鍙ｏ紱褰撳墠闈犳墽琛屽櫒鍐茬獊鏄犲皠鍏抽棴鎴愬姛鍐欏叆璺緞锛屼絾鏈疄鐜伴攣鎴栧箓绛夊崗璋冦€?5. callback 鍦ㄦ壘涓嶅埌鍒涘缓瀹¤鏃朵細杩斿洖缁撴瀯鍖栨湭鎵惧埌锛涚湡瀹炴寔涔呭寲鑻ヤ涪澶卞璁′簨浠讹紝浠嶆棤娉曟仮澶嶅師 request/run銆?
