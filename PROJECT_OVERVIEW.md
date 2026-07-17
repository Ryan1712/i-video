# Agent Video — Tổng quan dự án

Cập nhật: 2026-07-16

## 1. Sản phẩm này là gì

**Agent Video** là trợ lý (agent) sản xuất video kể chuyện/narration-driven **trọn gói** cho YouTube creator — **KHÔNG giới hạn ở một thể loại hay chủ đề cụ thể nào**, tạo được nhiều loại video khác nhau. Người dùng đưa vào ý tưởng sơ sài hoặc kịch bản đầy đủ (chủ đề bất kỳ), tool sẽ:

1. Viết kịch bản hoàn chỉnh đúng thời lượng yêu cầu (nếu đầu vào chỉ là ý tưởng) — AI viết nháp, user là tổng biên tập, luôn duyệt/sửa trước khi đi tiếp.
2. Chia cảnh, viết lời thoại từng cảnh, gán ảnh từ kho sẵn có của series hoặc sinh ảnh mới ngay trong tool.
3. Dựng video: giọng đọc TTS, phụ đề, hiệu ứng trên ảnh tĩnh, nhạc nền.
4. Cho chỉnh sửa trong timeline editor đa track trước khi render bản cuối (đang ở lộ trình, xem mục 6).
5. Upload YouTube.

Cấu trúc làm việc: **Series** (= một kênh/chủ đề bất kỳ) → nhiều **Episode**. Series giữ tài sản dùng chung: ảnh nhân vật/bối cảnh, style bible, giọng đọc, ngôn ngữ, phong cách phụ đề. **"What If: Zombie Apocalypse" chỉ là MỘT series mẫu đang dùng để phát triển và kiểm chứng pipeline end-to-end — hoàn toàn không phải giới hạn thể loại của sản phẩm.** Series tiếp theo có thể thuộc bất kỳ chủ đề nào: lịch sử, khoa học, review, giải thích khái niệm, tin tức, hư cấu, v.v.

Định vị cạnh tranh (theo spec sản phẩm v3): không cạnh tranh kiểu "script → video tự động" đại trà, mà cạnh tranh bằng khả năng giữ **nhất quán nhân vật/style/giọng đọc xuyên suốt nhiều tập** trong cùng một series.

Repo chứa **hai cách dùng song song** của cùng một engine dựng video:

1. **CLI local** (`agent_video/`) — chạy trên máy, người dùng tự viết `script.md`, tự chuẩn bị ảnh, engine lo TTS + Ken Burns + phụ đề + ghép video + upload YouTube.
2. **SaaS web** (`saas/` + `frontend/`) — FastAPI backend + Next.js frontend, có AI viết kịch bản, AI sinh ảnh, tài khoản người dùng, billing, admin panel. Dùng lại đúng engine core của CLI (không viết lại pipeline render).

## 2. Tech stack

### Backend / engine
- **Python 3.12**
- **FastAPI** (SaaS API) + **Uvicorn**
- **SQLAlchemy 2.0** + **PostgreSQL** (psycopg2)
- **Celery** + **Redis** (background job: build video, upload YouTube)
- **boto3** — object storage tương thích S3 (MinIO ở local/self-host)
- **Anthropic SDK** (`anthropic>=0.40.0`) — AI viết kịch bản, phân tích/chia scene, phê bình chất lượng script (model mặc định `claude-sonnet-5`, override qua `ANTHROPIC_MODEL`)
- **ElevenLabs API** (qua `requests`, không SDK riêng) — text-to-speech chính; **Azure Speech** là provider TTS thay thế
- **ElevenLabs Music API** — sinh nhạc nền theo prompt
- **imageio-ffmpeg** — bundle ffmpeg, dùng cho toàn bộ xử lý video/audio (Ken Burns, ghép clip, mux audio, phụ đề ASS)
- **Pillow** — xử lý ảnh
- **Google API Client + google-auth-oauthlib** — YouTube Data API v3 (OAuth + upload)
- **Stripe** + tự xây webhook chuyển khoản ngân hàng VN (SePay/Casso) — billing
- **PyJWT + passlib/bcrypt** — auth
- **cryptography (Fernet)** — mã hoá token OAuth lưu trong DB
- **pytest + moto** — test suite (346 test, toàn bộ pass)

### Frontend
- **Next.js 14** (App Router) + **React 18** + **TypeScript**
- **Tailwind CSS** + **shadcn** components + **@base-ui/react**
- **next-intl** — đa ngôn ngữ (route `/[locale]/...`)
- **Jest + Testing Library** (unit) + **Playwright** (E2E)

### Hạ tầng / triển khai
- **Docker Compose** (dev: `docker-compose.yml` + override cổng Postgres cục bộ; prod: `docker-compose.prod.yml`)
- **Nginx** reverse proxy + Let's Encrypt SSL (`scripts/setup_ssl.sh`)
- MinIO (S3-compatible) chạy trong container ở local/self-host

### Đã chốt nhưng CHƯA triển khai (roadmap Phase 2-3, xem mục 6)
- **Remotion** — thay renderer ffmpeg/Python hiện tại bằng Node worker dùng chung một composition React cho cả preview (`@remotion/player`) và render server, để preview = kết quả render thật. Lý do trì hoãn: pipeline ffmpeg hiện có là chi phí chìm đã chạy được — ưu tiên ra video thật trước khi đầu tư renderer mới.
- **Timeline editor đa track** (mức 2) trên nền composition Remotion — track cảnh/ảnh, giọng đọc, nhạc, phụ đề, text overlay; sửa lời thoại tự re-TTS + cảnh tự dồn.

## 3. Kiến trúc & luồng dữ liệu

```
Authoring                          Rendering
─────────                          ─────────
script.md (CLI, người viết)   ┐
                               ├─▶ ProductionPlan (v0.1, JSON) ─▶ TTS (có cache) ─▶ Ken Burns clip từng scene
DB: Episode + Scene rows (SaaS)┘                                                  ─▶ ghép video + phụ đề + nhạc nền
                                                                                    ─▶ output.mp4
```

- **`ProductionPlan`** (`agent_video/production_plan.py`, thêm 2026-07-16) là cấu trúc trung gian chuẩn hoá giữa "cách tạo nội dung" (markdown thủ công hoặc DB) và renderer — mọi build đều ghi ra `production_plan.json` làm artifact có thể tái tạo lại. Có khái niệm **section** (nhóm scene, mang `mood`/`intensity`/`music_profile` — hiện mới lưu, renderer chưa dùng tới, chờ bước làm nhạc theo section).
- **TTS content-hash cache** (`agent_video/tts_cache.py`, thêm 2026-07-16): key = SHA-256(provider + model + voice + settings + text + version). CLI cache tại `.tts_cache/` cạnh thư mục video; SaaS cache trong MinIO (`tts_cache/`, dùng chung mọi user). Sửa 1 câu narration → rebuild chỉ tốn phí TTS cho đúng scene đó, không phải toàn bộ episode.
- **Script Quality v0** (`agent_video/script_quality.py` + `saas/ai/script_quality_critic.py`, thêm 2026-07-16): công cụ CLI nội bộ (`scripts/check_script_quality.py`) — 12 rule regex/heuristic miễn phí (cliché, câu quá dài, cấu trúc lặp, từ nhấn mạnh lặp lại) + 1 lệnh gọi AI duy nhất phê bình toàn bộ episode, xuất ra report markdown. **Không tự sửa gì** — chỉ báo cáo, người quyết định sửa.

## 4. Tính năng đã build xong

### Engine dựng video (dùng chung CLI + SaaS)
- Parse kịch bản có cấu trúc section/scene (`script_parser.py`)
- Text-to-speech (ElevenLabs chính, Azure thay thế), có cache theo nội dung
- Ken Burns effect trên ảnh tĩnh → clip video (`image_builder.py`)
- Ghép các clip scene + audio + phụ đề ASS (`video_builder.py`, `captions.py`)
- Nhạc nền qua ElevenLabs Music API (`music.py`)
- Retry tự động cho lỗi mạng khi gọi TTS hàng loạt

### CLI (`python -m agent_video`)
- `new` — tạo khung episode mới (thư mục + `script.md` mẫu)
- `status` — kiểm tra đủ ảnh chưa (đối chiếu `assets/` + `assets_common/`)
- `build` — chạy toàn bộ pipeline, xuất `production_plan.json` + video
- `upload` — đăng YouTube (OAuth desktop app)

### SaaS backend (FastAPI)
- Auth (signup/login, JWT)
- Series: series bible tối giản (`style` JSON: voice, ngôn ngữ, nhạc, tts_provider...), thư viện asset dùng chung
- Episode: tạo, list, generate-script (AI), analyze-script (AI chia scene + gán ảnh từ catalog series), upload ảnh scene thủ công, generate-asset (AI sinh ảnh qua GPT-Image), build (job nền), lấy trạng thái job/output
- Billing: Stripe checkout + subscription, chuyển khoản ngân hàng VN (webhook), plan/voucher/giới hạn sử dụng
- YouTube: OAuth connect/callback/disconnect, upload job nền, token mã hoá Fernet
- Admin (**chỉ có API, chưa có giao diện**): quản lý plan, voucher, giao dịch, user, cấu hình hệ thống, audit log

### Frontend (Next.js)
- Landing page + i18n (VN/EN qua `next-intl`)
- Dashboard: episodes, series, billing, youtube connect
- Auth pages (login/signup)
- Chưa có: giao diện admin (chỉ có API), timeline editor (đã chốt trong roadmap Phase 3, chưa tới lượt build — xem mục 6)

## 5. Trạng thái hiện tại (2026-07-16)

- **EP1 đã dựng xong** nhiều lần lặp: bản SaaS gốc (episode 5, 8:05) và loạt bản CLI tiếng Anh (`output_en_v2/v3/v4.mp4`, episode 6) — **chưa upload YouTube** (chưa kết nối kênh nào).
- Ba tính năng nền tảng vừa merge vào `master` cùng ngày 2026-07-16: **TTS cache**, **ProductionPlan v0**, **Script Quality v0** — đều qua quy trình spec → plan → implement (subagent-driven) → code review độc lập, 346/346 test pass.
- Đã dùng Script Quality v0 để rà và **sửa thật nội dung episode 6** — 3 vòng lặp sửa/kiểm tra, giảm cảnh bị gắn cờ từ 19 xuống 13/37, giảm vấn đề AI-critic từ 5 xuống 1 (vấn đề còn lại là quyết định dựng phim — có nên gộp scene hay không — chưa tự động hoá).
- **Chưa** deploy production thật (có sẵn Dockerfile/nginx/SSL script nhưng chưa chạy trên server).
- **Chưa** review đầy đủ chất lượng giọng đọc/hình ảnh/âm thanh của EP1 bằng tai/mắt người (mới có phần script được rà bằng tool).

## 6. Định vị & lộ trình sản phẩm

**Lưu ý quan trọng khi đọc mục này:** có HAI lộ trình lồng nhau, đừng nhầm cái ngắn hạn thành định nghĩa lại sản phẩm.

### 6.1 Lộ trình cấu trúc dài hạn — spec chính thức (`docs/superpowers/specs/2026-07-10-product-vision-v3-design.md`)

1. **Phase 1 — Não AI + EP 1-3 THẬT** (đang làm, xem 6.2 bên dưới cho chi tiết thực thi): AI viết kịch bản + chia cảnh + sinh ảnh thiếu, dùng pipeline render ffmpeg hiện có (chưa đổi sang Remotion vội — pipeline cũ là chi phí chìm đã chạy được, ưu tiên có video thật sớm). **Định nghĩa "xong" của Phase 1: 3 video hoàn chỉnh thật trên YouTube.**
2. **Phase 2 — Render engine Remotion**: thay ffmpeg/Python bằng Node worker Remotion, composition JSON đa track, thêm Alembic cho migration.
3. **Phase 3 — Timeline editor mức 2** trên nền composition Phase 2: track cảnh/ảnh, giọng đọc, nhạc, phụ đề, text overlay; sửa lời thoại tự re-TTS cảnh đó và các cảnh sau tự dồn theo audio mới.
4. **Phase 4 — Đồng bộ SaaS để bán**: landing copy đúng định vị "series nhất quán", i18n giao diện đầy đủ, giới hạn theo gói, Google OAuth verification + xin tăng quota YouTube API.

Ba trụ cột giá trị xuyên suốt các phase: **Series intelligence** (nhớ style/giọng/nhân vật qua từng episode), **Structured production** (script/section/scene/visual/voice/audio đều có cấu trúc, không phải một file MP4 chết), **Selective control** (sửa đúng phần chưa tốt, không làm lại toàn bộ — đây là lý do có editor ở Phase 3).

### 6.2 Vòng lặp thực thi hiện tại — bên trong Phase 1, cách làm chi tiết bước "dựng EP 1-3 bằng pipeline cũ"

Đây KHÔNG phải lộ trình sản phẩm riêng, chỉ là cách chia nhỏ công việc kỹ thuật để không nhảy cóc vào kiến trúc lớn khi chưa có video thật nào được kiểm chứng:

1. ~~EP1 v0 end-to-end~~ ✓
2. Review EP1 có hệ thống (đang làm dở — phần script đã rà bằng Script Quality v0, phần voice/visual/audio còn chờ người nghe/xem)
3. ~~Content-hash cache~~ ✓
4. ~~ProductionPlan v0~~ ✓ (+ Script Quality v0, phát sinh thêm trong lúc làm)
5. Fix blocker lớn nhất (đang xác định — ứng viên hiện tại: giọng văn kịch bản, đã cải thiện một phần)
6. EP1 v1 hoàn chỉnh
7. EP2 khác format để test khả năng tổng quát hoá của kiến trúc (production_plan, cache, script quality...)
8. Sau đó mới quay lại Phase 2 (Remotion) / Phase 4 (deploy SaaS, thương mại hoá)

**Cố tình hoãn ở bước này** (không phải loại khỏi sản phẩm — chỉ chưa tới lượt, tránh over-engineering khi chưa có episode nào đăng thật): NarrationProfile/ScriptPlan với hàng chục tham số tinh chỉnh, multi-agent pipeline viết kịch bản, few-shot style reference, music theo section (dù `ProductionPlan` đã có chỗ lưu `mood`/`music_profile`), Series Bible đầy đủ, AI music generation toàn bộ, dependency graph engine, versioning đầy đủ.
