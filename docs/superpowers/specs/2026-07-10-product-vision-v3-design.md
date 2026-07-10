# Agent Video — Tầm nhìn sản phẩm v3 (AI viết kịch bản, sinh ảnh trong tool, timeline editor)

> **Thay thế `2026-07-04-product-vision-v2-design.md`.** Rà soát lại toàn bộ với chủ dự án ngày 2026-07-10. Các phần hạ tầng SaaS trong `2026-06-21-saas-platform-design.md` (auth, billing, admin, jobs, object storage) vẫn giữ nguyên hiệu lực. Task 1-3 của plan Phase 1 cũ (models Series/SeriesAsset, router series, link episodes) đã code xong và được giữ nguyên.

## Định nghĩa sản phẩm

Trợ lý sản xuất video kể chuyện trọn gói cho creator YouTube. Người dùng đưa vào **ý tưởng sơ sài hoặc kịch bản đầy đủ** + kho ảnh của series; tool:

1. Viết kịch bản hoàn chỉnh đúng thời lượng yêu cầu (nếu đầu vào là ý tưởng).
2. Chia cảnh, viết lời thoại từng cảnh, gán ảnh từ kho, báo ảnh thiếu kèm prompt mô tả.
3. Sinh ảnh thiếu ngay trong tool (hoặc user tự tạo ngoài rồi upload).
4. Dựng video: giọng đọc TTS, phụ đề, hiệu ứng trên ảnh tĩnh, transition, nhạc nền.
5. Cho chỉnh sửa trong **timeline editor đa track** trước khi render bản cuối.
6. Upload YouTube.

Cấu trúc làm việc: **Series** (= một kênh/chủ đề, ví dụ "What if zombie apocalypse", 10 tập) → nhiều **Episode**. Series giữ tài sản dùng chung: ảnh nhân vật/bối cảnh, style bible, giọng đọc, ngôn ngữ, phong cách phụ đề.

## Quyết định đã chốt (2026-07-10, thay các quyết định tương ứng của v2)

1. **Mục tiêu kép, một dòng công việc**: SaaS đa người dùng để bán, kiểm chứng bằng chính series của chủ dự án. Vì nguồn lực là một người + Claude Code, kênh và sản phẩm KHÔNG tách track — làm kênh bằng chính app là cách test sản phẩm. Thước đo sớm nhất: EP 1-3 thật trên YouTube.
2. **AI viết kịch bản** (đảo ngược v2): tool nhận ý tưởng + thời lượng đích → viết kịch bản đủ độ dài. Kịch bản luôn hiện cho user duyệt/sửa trước khi chia cảnh — AI là người viết nháp, user là tổng biên tập. Nếu user dán kịch bản đầy đủ thì bỏ qua bước viết.
3. **Sinh ảnh trong tool từ đầu** (kéo lên từ mục "Để sau" của v2): checklist ảnh thiếu có nút "Sinh ảnh" gọi API qua interface `ImageProvider` (bắt đầu: gpt-image; sau: Flux/Gemini). Prompt = mô tả cảnh do agent viết + `image_style_bible` của series + ảnh tham chiếu nhân vật từ kho (để giữ nhất quán). Ảnh sinh ra lưu vào `series_assets` với `source=generated` — tập sau dùng lại được. Upload ảnh tự tạo vẫn hỗ trợ song song.
4. **Editor mức 2 — timeline đa track** (nâng từ "theo cảnh 3a" của v2): track cảnh/ảnh, giọng đọc, nhạc, phụ đề, text overlay. Thao tác: kéo căn thời điểm, cắt/ghép cảnh, thay ảnh, sửa lời thoại (tự re-TTS cảnh đó, các cảnh sau tự dồn), sửa sub từng câu, đổi nhạc + âm lượng, thêm text/sticker overlay. NGOÀI phạm vi: keyframe animation tự do, multi-video-track chồng lớp, filter màu, chroma key, export gói CapCut.
5. **Đa ngôn ngữ theo series**: mỗi series có `language` (vi/en/...); kịch bản, giọng đọc, phụ đề theo ngôn ngữ series. Giao diện app i18n ở Phase 4.
6. **TTS**: interface đa provider (`synthesize(text, voice, language) -> audio + timestamps`) làm ngay Phase 1 (không chờ Phase 2 như v2) vì chất lượng giọng TIẾNG VIỆT là ẩn số lớn nhất. Trước EP 1: so sánh ElevenLabs / Azure / Gemini TTS trên cùng đoạn kịch bản VN. Dự phòng nếu giọng VN đều chưa đạt: series đầu làm tiếng Anh.
7. **Model LLM**: viết kịch bản + chia cảnh mặc định `claude-sonnet-5`, model ID nằm trong config/env (KHÔNG hardcode như plan cũ ghi `claude-opus-4-8`).
8. **Remotion cho render + preview** (giữ nguyên v2 — quyết định này đúng): một bộ composition React dùng chung cho preview (`@remotion/player`) và render server, bảo đảm preview = kết quả render. Timeline editor mức 2 buộc phải có nền này; ffmpeg + timeline đa track không khả thi về bảo trì.
9. **Thứ tự thực thi = Hướng A**: ra EP 1-3 bằng pipeline ffmpeg hiện có TRƯỚC, Remotion sau. Pipeline ffmpeg là chi phí chìm đã tồn tại; giá trị của video thật sớm (nuôi kênh + dạy ta editor cần gì) lớn hơn chi phí dùng tạm nó.
10. **Định vị thị trường** (giữ nguyên v2): không cạnh tranh "script → video tự động" đại trà; cạnh tranh bằng **series dài tập nhất quán** — nhân vật, style, giọng cố định xuyên tập.

## Pipeline AI (luồng làm một tập)

```
Ý tưởng sơ sài ──┐
                 ├─→ [1. Viết kịch bản] ─→ user duyệt/sửa ─→ [2. Chia cảnh + gán ảnh]
Kịch bản đầy đủ ─┘      (thời lượng đích)                            │
                                                    ┌────────────────┴────────┐
                                              cảnh có ảnh khớp         ảnh thiếu + prompt
                                                    │                  [3. Sinh ảnh / upload]
                                                    └────────┬─────────┘
                                                    [4. Build: TTS + phụ đề + hiệu ứng + nhạc]
                                                             │
                                              [5. Editor timeline] ⇄ re-TTS từng cảnh
                                                             │
                                                    [6. Render] → [7. Upload YouTube]
```

- **Bước 1** `POST /episodes/{id}/generate-script`: input `brief`, `target_duration_sec`; quy đổi thời lượng → số từ theo tốc độ đọc TTS (~140-160 từ/phút, hệ số riêng vi/en). Độ dài kiểm soát ±15-20% là chấp nhận được — thời lượng thật do audio TTS quyết định, đo được sau khi synth; nếu lệch nhiều cho phép yêu cầu AI viết thêm/cắt bớt.
- **Bước 2** `POST /episodes/{id}/analyze-script`: Claude structured outputs, input = kịch bản + catalog `series_assets` (name, kind, description) → output scenes (narration, asset khớp hoặc `asset_brief` mô tả ảnh cần tạo, hiệu ứng gợi ý).
- **Bước 3** `POST /episodes/{id}/scenes/{sid}/generate-asset` (hoặc theo asset_brief): gọi `ImageProvider`, lưu S3 + `series_assets`.
- **Bước 4-7**: pipeline build hiện có (Celery TTS → ffmpeg) ở Phase 1; Remotion từ Phase 2; editor từ Phase 3.

## Thay đổi dữ liệu (đắp thêm lên Task 1-3 đã xong)

```
series.style jsonb  -- thêm khóa: language, image_style_bible,
                    -- voice_id, tts_provider, caption_style, default_music_object_key

series_assets
  + source (uploaded|generated)   -- ảnh sinh bởi tool hay user upload

episodes
  + brief TEXT                    -- ý tưởng gốc user nhập
  + target_duration_sec INT NULL
  + composition jsonb             -- trạng thái timeline editor (từ Phase 2)

scenes                            -- (đã có asset_brief từ Task 1)
  + motion_type (static)          -- chừa chỗ ai_video sau này
  + effect jsonb                  -- { type: kenburns|parallax, params }
  + transition (cut|fade|...)
  + duration_override_ms NULL     -- mặc định theo audio TTS
```

`composition` là JSON đa track (scenes/voiceover/music/subtitles/overlays) theo schema composition props của Remotion; khi chưa vào editor được sinh tự động từ `scenes`. Phụ đề sinh từ text kịch bản (chính xác 100% chữ) + timestamps do TTS provider trả về.

## Kiến trúc render

- **Phase 1**: giữ nguyên pipeline build hiện có (Celery + ffmpeg). Không đầu tư thêm vào ffmpeg.
- **Phase 2**: Node render worker chạy Remotion — nhận job từ Redis, tải assets + audio từ S3/MinIO, render mp4, ghi S3, cập nhật `jobs`. Celery vẫn làm TTS + upload YouTube. `progress_pct` cập nhật 2 bước (TTS, render).
- Giữ nguyên: FastAPI, Postgres, Redis, MinIO/S3, toàn bộ auth/billing/admin.
- **Alembic** được thêm ở đầu Phase 2, trước khi schema bắt đầu đổi nhiều (hiện tại ALTER tay trên dev DB còn chịu được).

## Timeline editor (Phase 3)

- Trang `/dashboard/episodes/{id}/edit`: `@remotion/player` preview + timeline UI tự xây (React).
- Tracks: cảnh (ảnh + hiệu ứng), giọng đọc, nhạc nền, phụ đề, text overlay.
- Nguyên tắc narration-driven: sửa lời thoại → re-TTS cảnh đó → cảnh tự co giãn theo audio mới → các cảnh sau tự dồn. Kéo-thả chỉ căn chỉnh trong phạm vi cảnh/overlay, không phá ràng buộc audio-cảnh.
- Lưu = ghi `composition` jsonb (validate schema ở API, 422 kèm đường dẫn field lỗi). Render = enqueue job build với composition hiện tại.

## Lộ trình (mỗi phase một chu trình spec-chi-tiết → plan → code)

1. **Phase 1 — Não AI + EP 1-3 THẬT** (branch `phase1-series-agent` đang dở):
   giữ Task 1-3 đã xong; so sánh giọng TTS tiếng Việt (trước EP 1); TTS provider interface; generate-script + analyze-script; nút sinh ảnh thiếu; frontend flow (series → episode → nhập ý tưởng/kịch bản → duyệt kịch bản → checklist ảnh → build); dựng EP 1-3 bằng pipeline cũ. **Định nghĩa xong: 3 video hoàn chỉnh trên YouTube.**
2. **Phase 2 — Render engine Remotion**: Node worker, composition schema đa track, hiệu ứng (Ken Burns, parallax, transitions, text, nhạc/SFX), Alembic.
3. **Phase 3 — Timeline editor mức 2** trên composition của Phase 2.
4. **Phase 4 — Đồng bộ SaaS**: landing copy theo định vị "series nhất quán" (copy hiện tại sai), i18n giao diện EN/VI, giới hạn theo gói (số series, phút render/tháng, số ảnh sinh/tháng), TTS provider giá rẻ cho gói thấp, sửa `GET /billing/subscription` 404, Google OAuth verification + xin tăng YouTube API quota (mặc định 10.000 units/ngày ≈ 6 upload/ngày toàn hệ thống — nộp trước khi mở cho khách; test kênh cá nhân không vướng).

## Bên thứ 3 và chi phí vận hành

| Việc | Dịch vụ | Chi phí ước tính |
|---|---|---|
| Viết kịch bản + chia cảnh | Claude API (`claude-sonnet-5`, config được) | ~0.1-0.3$/tập |
| Sinh ảnh thiếu | gpt-image qua `ImageProvider` (sau: Flux/Gemini) | ~0.02-0.19$/ảnh; ~0.5-3$/tập |
| Giọng đọc | ElevenLabs / Azure / Gemini TTS qua interface chung — chốt sau khi so giọng VN | ~1-3$/tập 10 phút (ElevenLabs); ~0.15$/tập (OpenAI/Azure) |
| Render + preview | Remotion | miễn phí ≤3 người; Company License khi vượt |
| Nhạc nền | Thư viện license thương mại rõ ràng hoặc user upload | KHÔNG dùng nhạc trôi nổi khi bán SaaS |
| Lưu trữ | MinIO dev / Cloudflare R2 prod | ~0 quy mô đầu |
| Thanh toán / YouTube | Stripe + SePay / YouTube Data API (đã có) | — |
| Để sau | Kling/Runway (image-to-video, đã chừa `motion_type`) | ~0.5-1$/clip 5-10s |

**Tổng ~2-6$/tập 10 phút** — cơ sở định giá gói SaaS sau này.

## Rủi ro đã nhận diện và cách xử lý

1. **Nhất quán nhân vật khi sinh ảnh** (trung bình): giảm bằng ảnh tham chiếu từ kho series + style bible trong prompt; lưới an toàn là sinh lại/upload tay. Phong cách stick figure đơn giản chịu rủi ro này thấp hơn ảnh tả thực.
2. **Chất lượng giọng TTS tiếng Việt** (ẩn số): test so sánh trước EP 1; dự phòng làm series tiếng Anh trước.
3. **Độ dài kịch bản lệch thời lượng đích**: chấp nhận ±15-20%, đo bằng audio thật, cho phép viết thêm/cắt.

## Xử lý lỗi

- LLM trả sai schema (generate-script / analyze-script) → retry 1 lần kèm lỗi, sau đó `ERR_SCRIPT_ANALYSIS_FAILED` / `ERR_SCRIPT_GENERATION_FAILED`; user vẫn viết/chia tay được.
- Sinh ảnh lỗi → `ERR_IMAGE_GENERATION_FAILED`, mục checklist giữ trạng thái thiếu, cho bấm lại.
- Render worker lỗi → job `failed` + `error_message`, episode quay về trạng thái trước (pattern hiện có).
- Composition sai schema → validate ở API trước khi enqueue, 422 kèm đường dẫn field lỗi.

## Kiểm chứng end-to-end (định nghĩa "xong" của v3)

1. Tạo series "zombie apocalypse" (language, style bible, giọng đã chốt qua test VN) + upload ảnh nhân vật dùng chung.
2. Tạo episode, nhập ý tưởng + thời lượng 8 phút → AI viết kịch bản → duyệt/sửa → chia cảnh, báo đúng ảnh thiếu.
3. Bấm sinh 1 ảnh thiếu trong tool + upload 1 ảnh tự tạo → build → video có giọng đọc, phụ đề đúng chữ, chuyển động, nhạc.
4. (Từ Phase 3) Trong editor: đổi thứ tự 2 cảnh, sửa lời thoại 1 cảnh (re-TTS), thêm text overlay → render đúng như preview.
5. Upload YouTube từ bản render cuối.
6. Hai người dùng khác nhau không thấy series/assets của nhau; giới hạn gói kiểm tra khi tạo series/build/sinh ảnh.
