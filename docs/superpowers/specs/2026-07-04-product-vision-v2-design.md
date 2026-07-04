# Agent Video — Tầm nhìn sản phẩm v2 (Series, Agent chia cảnh, Remotion editor)

> **Thay thế một phần các spec cũ.** Spec `2026-06-21-video-engine-design.md` mô tả sản phẩm là công cụ cho MỘT kênh "What If" và định vị sai vai trò của AI. Chủ dự án xác nhận (2026-07-04) tầm nhìn đúng như tài liệu này. Các phần hạ tầng SaaS trong `2026-06-21-saas-platform-design.md` (auth, billing, admin, jobs, object storage) **vẫn giữ nguyên hiệu lực**.

## Bối cảnh và định nghĩa sản phẩm

SaaS "trợ lý sản xuất video YouTube" cho creator làm kênh nội dung kể chuyện (what-if, zombie apocalypse, giả tưởng...). Cấu trúc làm việc:

- **Series** = một dự án/chủ đề kênh (ví dụ "What if the world apocalypse with zombies", 10 tập).
- **Episode** thuộc series. Với mỗi episode, người dùng cấp: kịch bản (text) + assets ảnh (nhân vật, bối cảnh, đồ vật).
- **Agent AI** (Claude API) đọc kịch bản → tự chia thành các cảnh, viết lời thoại từng cảnh, gán ảnh phù hợp từ kho assets, và xuất **checklist ảnh còn thiếu kèm mô tả chi tiết** để người dùng đem đi tạo (ChatGPT/Midjourney — app KHÔNG tự sinh ảnh ở v2, xem "Để sau").
- App dựng video: giọng đọc TTS (ElevenLabs), phụ đề, chuyển động trên ảnh tĩnh (Ken Burns/parallax), transition, nhạc nền.
- **Timeline editor** trong web cho phép chỉnh sửa trước khi render bản cuối và đăng YouTube.

Quyết định đã chốt với chủ dự án:
1. Vẫn là **SaaS đa người dùng** (không phải tool cá nhân) — mọi tính năng thiết kế multi-tenant.
2. Pipeline hình ảnh: **toàn ảnh tĩnh + hiệu ứng** (phương án A) — chi phí biến đổi ~0/tập. Mỗi cảnh có trường `motion_type` (v2 chỉ có `static`) để sau này bật `ai_video` (Kling/Runway) mà không đổi kiến trúc.
3. Editor: **timeline editor thật trong web**, xây trên **Remotion** (phương án 1) — một bộ code React composition dùng chung cho preview trong trình duyệt (`@remotion/player`) và render server, bảo đảm preview = kết quả render.

## Thay đổi dữ liệu

```
series (MỚI)
  id, user_id, name, description,
  style jsonb  -- { voice_id, caption_style, default_music_object_key, ... }
  created_at

series_assets (MỚI)  -- ảnh nhân vật/bối cảnh dùng lại xuyên các tập
  id, series_id, kind (character|location|object|other),
  name, description, object_key, created_at

episodes
  + series_id FK (nullable trong migration, bắt buộc với episode mới)
  + composition jsonb  -- trạng thái timeline của editor (nguồn sự thật để render)

scenes
  + motion_type (static)      -- chừa chỗ cho ai_video
  + effect jsonb              -- { type: kenburns|parallax, params }
  + transition (cut|fade|...)
  + duration_override_ms (nullable, mặc định theo audio TTS)
```

`composition` là JSON mô tả tracks (scenes/voiceover/music/text-overlays) theo schema của Remotion composition props. Khi chưa vào editor, composition được sinh tự động từ `scenes`.

## Kiến trúc render

- Thay `video_builder` (Python/ffmpeg) bằng **Node render worker chạy Remotion**: nhận job từ Redis, tải assets + audio từ S3/MinIO, render mp4, ghi kết quả lên S3, cập nhật `jobs` qua API nội bộ hoặc ghi DB trực tiếp.
- Giữ nguyên: FastAPI, Celery (TTS + upload YouTube vẫn là task Python), Postgres, Redis, MinIO/S3, toàn bộ auth/billing/admin.
- TTS per-scene vẫn do Celery gọi ElevenLabs, file mp3 lưu S3; composition tham chiếu object key.
- Job `build` mới: Celery làm TTS xong → đẩy job render sang queue của Node worker → worker render → done. `progress_pct` cập nhật theo 2 bước (TTS x%, render y%).

## Timeline editor

- Trang `/dashboard/episodes/{id}/edit`: `@remotion/player` preview + timeline UI tự xây (React).
- Tracks: cảnh (ảnh + hiệu ứng), giọng đọc, nhạc nền, text overlay.
- Thao tác v2: đổi thứ tự cảnh, cắt/kéo dài cảnh, sửa lời thoại (re-TTS cảnh đó), thay ảnh, đổi hiệu ứng/transition, thêm/sửa text overlay, đổi nhạc, chỉnh âm lượng.
- Lưu = ghi `composition` jsonb. Render = enqueue job build với composition hiện tại.
- Ngoài phạm vi v2: keyframe tự do, multi-video-track, filter màu, export gói CapCut.

## Lộ trình (mỗi phase một chu trình spec-chi-tiết → plan → code)

1. **Phase 1 — Series + Agent chia cảnh**: bảng `series`/`series_assets`, UI quản lý series, endpoint `POST /episodes/{id}/analyze-script` dùng Claude API trả về scenes + asset checklist. Render vẫn dùng pipeline cũ.
2. **Phase 2 — Render engine Remotion**: Node worker, composition schema, hiệu ứng (Ken Burns, parallax, transitions, text, nhạc/SFX), thay pipeline ffmpeg.
3. **Phase 3 — Timeline editor** trên composition của Phase 2.
4. **Phase 4 — Đồng bộ SaaS**: viết lại landing copy đúng sản phẩm (copy hiện tại quảng cáo sai "AI writes the script, produces the scenes"), i18n EN/VI, giới hạn theo gói (số series, phút render/tháng), sửa `GET /billing/subscription` 404.

## Bên thứ 3

| Việc | Dịch vụ | Ghi chú chi phí |
|---|---|---|
| Giọng đọc | ElevenLabs (đã có) | ~1-3$/tập 10 phút |
| Agent chia cảnh | Claude API | ~0.05-0.2$/lần phân tích |
| Render + preview | Remotion | Company License khi SaaS có doanh thu |
| Lưu trữ | MinIO dev / Cloudflare R2 prod | ~0 quy mô đầu |
| Thanh toán / YouTube | Stripe + SePay / YouTube Data API (đã có) | — |
| Để sau | Kling/Runway (image-to-video), Flux/gpt-image (sinh ảnh thiếu) | bật theo gói cước, ~0.5-1$/clip 5-10s |

## Xử lý lỗi

- Phân tích kịch bản thất bại (LLM trả sai schema) → retry 1 lần với lỗi đính kèm, sau đó trả `ERR_SCRIPT_ANALYSIS_FAILED`, người dùng vẫn chia cảnh tay được.
- Render worker lỗi → job `failed` + `error_message`, episode quay về `draft`/`built` trước đó (giữ nguyên pattern upload YouTube hiện tại).
- Composition jsonb sai schema → validate ở API trước khi enqueue, trả 422 với đường dẫn field lỗi.

## Kiểm chứng end-to-end (định nghĩa "xong" của v2)

1. Tạo series "zombie apocalypse" với style + ảnh nhân vật dùng chung; tạo episode, dán kịch bản, agent chia cảnh và báo đúng ảnh thiếu.
2. Cấp đủ ảnh → build → video có giọng đọc, phụ đề, chuyển động, nhạc — preview trong editor giống hệt file render.
3. Trong editor: đổi thứ tự 2 cảnh, sửa lời thoại 1 cảnh (re-TTS), thêm text overlay → render lại đúng như preview.
4. Upload YouTube từ bản render cuối.
5. Hai người dùng khác nhau không thấy series/assets của nhau; giới hạn gói được kiểm tra khi tạo series/build.
