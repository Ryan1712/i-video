# Pre-production punch list (từ final review branch phase1-series-agent, 2026-07-10)

Các mục KHÔNG chặn merge Phase 1, nhưng PHẢI xử lý trước khi deploy production / mở SaaS cho khách. Nguồn: final whole-branch review 84dde4b..fef06dc.

## Chặn trước khi deploy production

1. **Quota/rate-limit cho 3 endpoint AI trả phí** (`generate-script`, `analyze-script`, `generate-asset`): hiện user free có thể loop không giới hạn, đốt Anthropic/OpenAI key của platform. Gắn vào plan limits (Phase 4 spec v3 đã dự trù "số ảnh sinh/tháng").
2. **Gọi ngoài đồng bộ trong request handler**: script generation + image generation chạy sync trong API request; nginx prod (`proxy_read_timeout` 60s) sẽ giết request. Chuyển sang Celery job (nhất quán với build flow) hoặc tối thiểu nâng timeout nginx cho các route này.

## Việc đầu tiên NGAY SAU EP 1 (user chốt 2026-07-13)

0. **Voice picker + series settings**: `GET /voices` (proxy API provider, cache, lọc theo ngôn ngữ) + dropdown chọn giọng kèm nút nghe thử trong form series + `PUT /series/{id}` để sửa style sau khi tạo. Lý do: hiện phải dán raw voice ID — trải nghiệm dev, không bán được cho user thường.

## Nên xử lý sớm (trước/trong khi làm EP 1)

3. ~~**`IMAGE_SIZE` mặc định `1536x1024` (3:2) không khớp khung video 16:9**~~ — **Đã quyết (2026-07-14): giữ nguyên `1536x1024`.** `gpt-image-1` chỉ hỗ trợ `1024x1024` / `1536x1024` / `1024x1536` / `auto` — không có `1792x1024` (đó là size của DALL-E 3, không áp dụng). `1536x1024` (tỉ lệ 1.5) là lựa chọn gần 16:9 (1.778) nhất trong các size hỗ trợ. Pipeline (`agent_video/image_builder.py::_cover_resize`) đã center-crop "cover" (không letterbox), chỉ cắt ~8% mép trên/dưới. Đã thêm hint vào system prompt của `analyze_script` (`saas/ai/script_analysis.py`) yêu cầu model giữ chủ thể/mặt nhân vật ở giữa khung dọc để tránh bị cắt.
4. **Scene bị thay khi re-analyze để rò object S3** (`episodes/{id}/scenes/{scene_id}.png` mồ côi); generate-asset lặp lại trên cùng scene tạo SeriesAsset + object mới mỗi lần (rác catalog). Cần chiến lược dọn.
5. ~~**`generate-script` và `generate-asset` thiếu draft guard**~~ — **Đã sửa (2026-07-14):** cả 2 endpoint (`saas/routers/episodes.py`) giờ trả `409 ERR_EPISODE_NOT_DRAFT` nếu `episode.status != "draft"`, cùng pattern với `analyze-script` đã có sẵn. Frontend không cần sửa: `ScriptPanel` đã disable khi episode không phải draft và `errors.ERR_EPISODE_NOT_DRAFT` đã có sẵn trong catalog i18n.

## Theo dõi

6. `GenerateScriptIn.target_duration_sec` chưa có bounds ở API (frontend giới hạn 1-60 phút) — thêm `Field(ge=60, le=3600)`.
7. Catalog assets nhúng vào system prompt (script_analysis) — cân nhắc chuyển sang user message để giảm bề mặt prompt injection (output đã được validate nên rủi ro thấp).
8. N+1 count query trong `list_series` — chưa đáng kể ở quy mô hiện tại.
9. Flaky 1/4 lần chạy full frontend suite (nghi timer leak trong dashboard.test.tsx, có từ trước branch này) + lỗi lint `next build` có sẵn (unused vars trong tests, exhaustive-deps) — dọn trong một commit riêng.
10. Minor tồn đọng từ per-task review: asset_id==0 falsy guard, magic number 2 trong ai/client, prompt hint "≈0 minutes" khi <60s, test coverage bổ sung (max_tokens/system forwarding, source="generated" round-trip, page-level test cho episode detail).
