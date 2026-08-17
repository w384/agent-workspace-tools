# Task 2 Brief 鈥?鍙俊 session銆丟ate 1 涓婁紶涓庣増鏈姸鎬佸洖鍐?
鍏堝畬鏁撮槄璇?`control_plane/docs/implementation-plan.md` 鐨?Global Constraints 涓?Task 2锛屽苟璇诲彇 Task 1 宸蹭氦浠樼殑 `domain.py`銆乣policy.py`銆乣repository.py`銆傝繖鏄湰浠诲姟鐨勭簿纭竟鐣屻€?
## 浜や粯鏂囦欢

- `control_plane/app/sessions.py`
- `control_plane/app/ports.py`
- `control_plane/app/service.py`
- `control_plane/app/main.py`
- `control_plane/tests/conftest.py`
- `control_plane/tests/test_session_boundary.py`
- `control_plane/tests/test_gate1_upload.py`

鍙负淇濊瘉娓呮櫚鑰屽皬骞呬慨鏀?Task 1 鏂囦欢鍜屽搴旀祴璇曪紝浣嗕笉寰楀疄鐜?Task 3/4銆?
## 鍥哄畾鎺ュ彛涓庡畨鍏ㄨ鍒?
1. `ServerSessionStore`锛氭湇鍔＄淇濆瓨 session锛宑ookie 浠呮寔鏈夐殢鏈?bearer锛涗粨鍌ㄥ彧淇濆瓨鍏?SHA-256 digest銆傜櫥褰曞嚟鎹潵鑷?`create_app` 娉ㄥ叆鐨勬紨绀鸿韩浠介厤缃紝浠?`hmac.compare_digest` 鏍￠獙锛涗笉寰楀啓姝荤敓浜у瘑閽ャ€俢ookie 鍚?`cp_session`锛宍HttpOnly`銆乣SameSite=Strict`锛屼繚鎶よ矾鐢卞彧浠?cookie 鏋勯€?`TrustedActorContext`銆?2. 浠讳綍 query/body/header 涓殑 `user_id` 蹇呴』琚拷鐣ワ紱`GET /api/session/me?user_id=user-b` 鍦?A cookie 涓嬩粛杩斿洖 A銆?3. `POST /api/session/login` 浠呬负鏈湴 DEMO 鐧诲綍锛涜繑鍥?actor/workspace/context/roles锛屼笉杩斿洖 session bearer 姝ｆ枃銆俙POST /api/session/logout` 浣挎湇鍔＄ session 澶辨晥銆?4. `FileExecutorPort.upload(actor, directory, file_name, content, request_id) -> UploadResult`銆俙UploadResult` 蹇呴』绮剧‘娑堣垂鎵ц鍣ㄥ搷搴斿瓧娈?`path/name/size_bytes/content_fingerprint`锛沗content_fingerprint` 蹇呴』涓?`sha256:<digest>` 鏍煎紡銆侭FF 涓嶈绠楁鏂?SHA-256锛屼笉鑷鎴愪负鏂囦欢鏉冨▉銆?5. `RagPort.enqueue_version(actor, asset_version, request_id) -> None`锛涙湰浠诲姟鍙仛褰曞埗妗╋紝涓嶅疄鐜拌В鏋?妫€绱€?6. `POST /api/uploads`锛氱敤鍙俊 actor 瀵规渶缁堢浉瀵硅矾寰勫仛 `UPLOAD` 鎺堟潈锛涙巿鏉冪洰褰曞唴銆侀潪瑕嗙洊鍥哄畾涓?`DIRECT`銆俙DENY` 鏃朵笉寰楄皟鐢?executor銆佷笉寰楀缓 Asset/Version銆傛垚鍔熷悗鎸?`(workspace_id, path)` get-or-create Asset锛屽垱寤?queued AssetVersion锛岃皟鐢ㄤ竴娆?RAG enqueue锛屽苟杩藉姞鍏宠仈 AuditEvent銆傚搷搴斿寘鍚?decision銆乤sset銆乤sset_version銆乤udit_event_id銆?7. 鍐呴儴鍥炶皟 `POST /internal/asset-versions/{id}/index-status` 蹇呴』鏍￠獙 `X-Internal-Service-Key`锛堟敞鍏ヤ笖闈炵┖锛夛紱body 涓?`state` 涓庡彲閫?`failure_code`銆傚鐢?Task 1 鐘舵€佹満锛歲ueued鈫抪arsing鈫抜ndexed鈫抮eady 鎴?non-ready鈫抐ailed銆傚け璐?v2 涓嶆浛鎹?ready v1 active銆備笉寰楀厑璁稿鎴风鐢ㄦ埛鍏ュ彛璋冪敤姝よ兘鍔涖€?8. 涓烘祴璇曡€屼娇鐢?`RecordingFileExecutor` / `RecordingRagPort` 鍙互鏀惧湪 `control_plane/tests/conftest.py`锛岀敓浜?ports 鍙斁 Protocol/dataclass锛屼笉濉炴祴璇曚笓鐢ㄥ疄鐜般€?9. FastAPI 閿欒浣跨敤缁撴瀯鍖?`{error:{code,message}}`锛涙湭鐧诲綍 401锛孉CL deny 403锛屽唴閮?key 閿欒 401锛岄潪娉曠姸鎬?409銆?
## 蹇呮祴琛屼负

- A 鐧诲綍鍚庝吉閫?`user_id=B` 涓嶆敼鍙?`/api/session/me` 鍜屼笂浼犺皟鐢ㄤ腑鐨?actor銆?- 鏃?cookie 涓嶈兘璁块棶淇濇姢 API锛沴ogout 鍚?cookie 澶辨晥銆?- A 鑾锋巿鏉?upload grant 鏃跺緱鍒?DIRECT锛涙墽琛屽櫒鎭板ソ璋冪敤涓€娆★紝涓旀敹鍒?A 鐨勫彲淇?actor銆?- AssetVersion 鐨?fingerprint 涓庢墽琛屽櫒杩斿洖鐨?`sha256:executor-digest` 瀹屽叏鐩哥瓑锛涙祴璇曞涓婁紶 content 浣跨敤鍙︿竴鍊硷紝璇佹槑娌℃湁琚?BFF 閲嶇畻銆?- 瓒婃潈涓婁紶 executor/RAG 鍧囬浂璋冪敤锛宺epository 涓嶄骇鐢?AssetVersion銆?- index 鐘舵€侀摼鑳戒娇 v1 ready锛泇2 failed 鍚?v1 浠?active锛涢潪娉曡烦璺冭繑鍥?409銆?- audit 鑷冲皯璁板綍 `upload_authorized`銆乣asset_version_created`銆乣asset_version_state_changed` 骞跺彲鐢ㄥ悓涓€ request_id 鍏宠仈銆?
## TDD 涓庨獙璇?
1. 鍏堝啓娴嬭瘯骞跺疄闄呰繍琛岋紝纭鍥犳ā鍧?璺敱缂哄け鑰?RED锛涙妸鍛戒护鍜屾憳瑕佸啓鎶ュ憡銆?2. 鍐嶅啓鏈€灏忓疄鐜帮紝杩愯锛?
```powershell
& 'D:\AI\Codex\Projects\agent-workspace-tools\service\.venv\Scripts\python.exe' -B -m pytest control_plane\tests\test_policy.py control_plane\tests\test_schema.py control_plane\tests\test_session_boundary.py control_plane\tests\test_gate1_upload.py -q -p no:cacheprovider
```

3. 鍐?`control_plane/work/sdd/control-plane-demo/task-2-report.md`锛屽惈 RED/GREEN 鍘熷鎽樿銆佹枃浠舵竻鍗曘€佽嚜瀹°€佹湭楠岃瘉椤广€?4. 鍙敼 `control_plane/**`锛屼笉瀹夎銆佷笉鎻愪氦銆佷笉鎺ㄩ€併€佷笉璁块棶鐪熷疄鍏叡鐩橈紱閫愭枃浠跺啓涓枃 `project-changes.log`銆?
