# Task 1 Brief 鈥?棰嗗煙妯″瀷銆佸洓鎬佺瓥鐣ヤ笌 PostgreSQL Schema

鍏堝畬鏁撮槄璇?`control_plane/docs/implementation-plan.md` 鐨?Global Constraints 涓?Task 1锛涗簩鑰呮槸鏈换鍔＄殑绮剧‘闇€姹傘€?
## 浜や粯鏂囦欢

- `control_plane/__init__.py`
- `control_plane/app/__init__.py`
- `control_plane/app/domain.py`
- `control_plane/app/policy.py`
- `control_plane/app/repository.py`
- `control_plane/migrations/001_control_plane.sql`
- `control_plane/tests/test_policy.py`
- `control_plane/tests/test_schema.py`

## 寮哄埗鎺ュ彛

- `evaluate_authorization(actor, grants, action, paths, overwrite=False) -> AuthorizationDecision`
- `DecisionState`: `DIRECT / SELF_CONFIRM / APPROVAL_REQUIRED / DENY`
- `Action`: `UPLOAD / CREATE_FOLDER / MOVE_RENAME / TRASH / QUERY`
- 瑙勫垯锛氭棤鎺堟潈銆侀潪娉曡矾寰勬垨鏄惧紡鎷掔粷 -> `DENY`锛涙巿鏉?`trash` -> `APPROVAL_REQUIRED`锛涙巿鏉?`move_rename/create_folder` -> `SELF_CONFIRM`锛涙巿鏉冧笖涓嶈鐩栫殑 `upload` 鍙婃巿鏉?`query` -> `DIRECT`锛涜鐩栦笂浼?-> `DENY`銆?- `ControlPlaneRepository` Protocol 涓庡彲鐢ㄤ簬鍚庣画 API 娴嬭瘯鐨?`InMemoryControlPlaneRepository`銆?- PostgreSQL DDL 蹇呴』瑕嗙洊 User/Group/Role銆丄sset銆丄ssetVersion銆丳ermissionGrant銆丳lan銆丆onfirmation銆丄pproval銆丒xecutionJob銆丄uditEvent銆丆hunkMetadata锛屽苟鍚繀瑕佷富閿€佸閿€佸敮涓€绾︽潫鍜岀姸鎬?CHECK銆?
## TDD 璇佹嵁

1. 鍏堝垱寤烘祴璇曞苟杩愯锛屼繚瀛橀鏈熷け璐ユ憳瑕併€?2. 鍐嶅啓鏈€灏忓疄鐜板苟杩愯鍚屼竴鍛戒护鑷抽€氳繃銆?3. 杩愯锛?   `& 'D:\AI\Codex\Projects\dify-agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_policy.py control_plane\tests\test_schema.py -q -p no:cacheprovider`
4. 涓嶄慨鏀?`control_plane/**` 涔嬪浠讳綍椤圭洰鏂囦欢锛涗笉鎻愪氦銆佷笉鎺ㄩ€併€?5. 姣忎釜鏂囦欢鍙樻洿鍚庢寜椤圭洰瑙勫垯璁板綍鍒?`D:\AI\Codex\Codex\2026\08\13\project-changes.log`锛屼笉寰楄褰曞瘑閽ャ€?6. 灏嗘姤鍛婂啓鍏?`control_plane/work/sdd/control-plane-demo/task-1-report.md`锛屽寘鍚?RED 鍛戒护/杈撳嚭銆丟REEN 鍛戒护/杈撳嚭銆佹枃浠舵竻鍗曘€佽嚜瀹′笌閬楃暀闂銆?
