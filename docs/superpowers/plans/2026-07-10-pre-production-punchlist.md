# Pre-production punch list (từ final review branch phase1-series-agent, 2026-07-10)

Các mục KHÔNG chặn merge Phase 1, nhưng PHẢI xử lý trước khi deploy production / mở SaaS cho khách. Nguồn: final whole-branch review 84dde4b..fef06dc.

## Chặn trước khi deploy production

1. **Quota/rate-limit cho 3 endpoint AI trả phí** (`generate-script`, `analyze-script`, `generate-asset`): hiện user free có thể loop không giới hạn, đốt Anthropic/OpenAI key của platform. Gắn vào plan limits (Phase 4 spec v3 đã dự trù "số ảnh sinh/tháng").
2. **Gọi ngoài đồng bộ trong request handler**: script generation + image generation chạy sync trong API request; nginx prod (`proxy_read_timeout` 60s) sẽ giết request. Chuyển sang Celery job (nhất quán với build flow) hoặc tối thiểu nâng timeout nginx cho các route này.

## Việc đầu tiên NGAY SAU EP 1 (user chốt 2026-07-13)

0. **Voice picker + series settings**: `GET /voices` (proxy API provider, cache, lọc theo ngôn ngữ) + dropdown chọn giọng kèm nút nghe thử trong form series + `PUT /series/{id}` để sửa style sau khi tạo. Lý do: hiện phải dán raw voice ID — trải nghiệm dev, không bán được cho user thường.

## Nên xử lý sớm (trước/trong khi làm EP 1)

3. **`IMAGE_SIZE` mặc định `1536x1024` (3:2) không khớp khung video 16:9** — ảnh sinh ra sẽ bị crop/letterbox bởi pipeline ffmpeg. Quyết định trước khi sinh ảnh cho EP 1 (cân nhắc 1792x1024 nếu model hỗ trợ, hoặc chấp nhận crop Ken Burns).
4. **Scene bị thay khi re-analyze để rò object S3** (`episodes/{id}/scenes/{scene_id}.png` mồ côi); generate-asset lặp lại trên cùng scene tạo SeriesAsset + object mới mỗi lần (rác catalog). Cần chiến lược dọn.
5. **`generate-script` và `generate-asset` thiếu draft guard** — có thể ghi đè script/scene của episode đã built/uploading.

## Theo dõi

6. `GenerateScriptIn.target_duration_sec` chưa có bounds ở API (frontend giới hạn 1-60 phút) — thêm `Field(ge=60, le=3600)`.
7. Catalog assets nhúng vào system prompt (script_analysis) — cân nhắc chuyển sang user message để giảm bề mặt prompt injection (output đã được validate nên rủi ro thấp).
8. N+1 count query trong `list_series` — chưa đáng kể ở quy mô hiện tại.
9. Flaky 1/4 lần chạy full frontend suite (nghi timer leak trong dashboard.test.tsx, có từ trước branch này) + lỗi lint `next build` có sẵn (unused vars trong tests, exhaustive-deps) — dọn trong một commit riêng.
10. Minor tồn đọng từ per-task review: asset_id==0 falsy guard, magic number 2 trong ai/client, prompt hint "≈0 minutes" khi <60s, test coverage bổ sung (max_tokens/system forwarding, source="generated" round-trip, page-level test cho episode detail).
