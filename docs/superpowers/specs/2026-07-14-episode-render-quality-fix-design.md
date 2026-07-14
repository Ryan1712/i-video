# Fix EP 1 render quality: scene image selection, captions, voice

> Phát sinh sau khi user review bản build đầu tiên của EP 1 (2026-07-13/14, episode id 5 tiếng Việt và id 6 tiếng Anh, branch `phase1-series-agent`) và từ chối cả 3 mặt: giọng đọc, caption, hình ảnh zoom. User yêu cầu dừng vá lỗi từng phần, brainstorm lại kỹ thuật.

## Bối cảnh — 3 vấn đề, đã root-cause

1. **Giọng đọc dở** (user: "như cứt, như người Ấn Độ, accent chán, giọng kể chán"). Đã thử ElevenLabs voice `47rM9DW5VmjOw23BVHWi` cho cả tiếng Việt (đọc như người Anh đọc tiếng Việt) lẫn tiếng Anh (vẫn dở) — voice này không phù hợp, chưa từng được chọn có chủ đích, chỉ là giá trị mặc định ai đó dán vào `.env`.
2. **Caption quá to**, che gần kín ảnh. Root cause thật: `agent_video/captions.py` gộp cả narration dài (100-250 ký tự) của một scene thành 1 cue duy nhất hiện suốt cả scene, ở font 48px trên khung 1920px — đo thực nghiệm chỉ ~20 ký tự/dòng chứ không phải ~35 như ước tính ban đầu. Đã fix một phần (chia cue theo câu/dấu phẩy/từ, cap 55 ký tự, font 34px) nhưng user vẫn thấy nặng, và phát sinh thêm bug: caption đè lên chữ có sẵn trong ảnh UI mockup (asset `screen_emergency_alert` tự có chữ "Unusual violent incidents...").
3. **Ảnh zoom tới mức không thấy gì**. Root cause thật: KHÔNG phải bug Ken Burns (đã verify: zoompan 1.0→1.15 hoạt động đúng, zoom nhẹ nhàng trên asset tỉ lệ chuẩn). Vấn đề là catalog series có 4 loại asset (`location`/`character`/`object`/`other`) nhưng `analyze_script` chọn bừa 1 asset bất kỳ làm nền full-frame cho scene, rồi `_cover_resize` crop cứng để lấp đầy 1920x1080. Asset `object`/`other` (ảnh cắt rời nhân vật, icon, mockup UI) chưa từng được thiết kế để đứng một mình làm nền toàn khung — ví dụ `shadow_under_door.png` (kind=object) thực chất là một dải bóng mảnh 2172x724 trên nền checkerboard **đã bake cứng vào pixel** (không phải alpha thật, do lỗi export gốc), khi cover-crop vào 1920x1080 chỉ còn lại một mẩu vô nghĩa.

## Quyết định đã chốt (2026-07-14)

1. **Kiến trúc chọn ảnh scene**: `analyze_script` chỉ được match asset có `kind="location"` (hoặc asset trước đây đã AI-generate làm cảnh full-frame, `source="generated"`) làm nền. Asset `character`/`object`/UI-mockup KHÔNG được chọn làm nền full-frame nữa. Lọc ở phía server (Python, khi build catalog JSON gửi AI) — không dựa vào AI tự giác tuân theo prompt.
2. Khi không có `location` asset khớp, hệ thống dùng lại nhánh "no match" hiện có: viết `asset_brief` và generate ảnh MỚI — nhưng brief phải mô tả **toàn cảnh rộng 16:9**, không phải cắt cận nhân vật/vật thể đơn lẻ (ví dụ: "cảnh tay cầm điện thoại, quay rộng trong phòng ngủ" thay vì chỉ "tay cầm điện thoại").
3. `shadow_under_door.png` và các asset export lỗi khác không cần sửa riêng — chúng tự động bị loại khỏi pool chọn nền theo quyết định #1. Không mở rộng để hỗ trợ composite nhiều lớp (background + overlay) ở lần này — out of scope, xem mục "Ngoài phạm vi".
4. **Caption**: giảm font 34px → ~26px, thêm thanh nền đen bán trong suốt phía sau chữ (ASS `BorderStyle=3` + `BackColour`) thay vì chỉ viền chữ. Vừa giảm cảm giác "nặng chữ", vừa che được chữ có sẵn trong ảnh UI mockup bên dưới. Giữ nguyên logic chia cue theo câu/dấu phẩy/từ (cap 55 ký tự) — phần này đã đúng.
5. **Giọng đọc**: search thư viện voice ElevenLabs (lọc narration/documentary, giọng nam trầm) + 1-2 giọng Azure English neural (`en-US-GuyNeural`, `en-US-ChristopherNeural`), tổng hợp mẫu nghe thử gửi user chọn — cùng quy trình đã làm với tiếng Việt.
6. **Rollout**: code fix (lọc catalog, style caption) kèm test trước → xác định các scene EP 1 hiện dùng asset không phải `location` → regenerate ảnh cho các scene đó → chạy voice comparison, chờ user chọn → build lại EP 1 một lần, verify bằng cách sample nhiều frame rải khắp video (không chỉ spot-check 1-2 điểm như trước) → mới gửi user xem.

## Thiết kế chi tiết

### A. Lọc catalog trong `analyze_script`

- File: `saas/ai/script_analysis.py` (hàm `analyze_script`) và `saas/routers/episodes.py` (nơi build `catalog` từ `series.assets` trước khi gọi `analyze_script`).
- Đổi: catalog gửi cho AI chỉ gồm asset `kind == "location"`. Asset khác vẫn tồn tại trong DB/series (không xóa), chỉ không nằm trong candidate pool.
- System prompt cập nhật: bỏ mô tả "pick the best-matching asset id from the catalog" chung chung → nói rõ catalog chỉ là các cảnh nền (location), nếu narration là khoảnh khắc nhân vật/vật thể cụ thể mà không có nền phù hợp thì luôn viết `asset_brief` mô tả toàn cảnh rộng 16:9.
- Test: `tests/saas/test_script_analysis.py` — thêm case catalog có cả `location` và `character`, verify catalog JSON gửi AI (`captured["system"]`) không chứa asset `character`.

### B. Caption style

- File: `agent_video/config.py` (`DEFAULT_CONFIG["caption"]["font_size"]`: 34 → 26) và `agent_video/video_builder.py` (chỗ build `force_style`).
- `force_style` mới: `FontName={font},FontSize={font_size},BorderStyle=3,Outline=1,Shadow=0,BackColour=&H80000000,MarginV=40` (box nền đen ~50% alpha, giữ margin đáy hợp lý). Giá trị alpha/margin tinh chỉnh bằng render thử nghiệm thực tế trước khi chốt (như đã làm với font size).
- Không đổi `agent_video/captions.py` (logic chia cue giữ nguyên, đã có test).

### C. Voice sourcing

- Script một lần (không phải endpoint mới): gọi `GET https://api.elevenlabs.io/v1/shared-voices` (hoặc `/v1/voices` nếu shared-voices không khả dụng với key hiện tại) lọc use_case narration, cộng thêm Azure `en-US-GuyNeural`/`en-US-ChristopherNeural`, synthesize cùng 1 đoạn mẫu tiếng Anh, xuất `videos/tts_compare_en/`. Không cần thay đổi code sản phẩm — đây là tác vụ một lần để chọn `voice_id` cấu hình cho series.
- Sau khi user chọn: update `series.style.voice_id` / `tts_provider` cho series id 2 (giống cách đã làm với `language`).

### D. Regenerate scene ảnh cho EP 1

- Xác định scene nào trong episode 6 hiện dùng asset không phải `location` (query DB, so khớp `asset_object_key` với catalog `kind`).
- Với mỗi scene đó: viết `asset_brief` mới (toàn cảnh 16:9 mô tả đúng khoảnh khắc) theo `image_style_bible` của series, gọi `saas/ai/image_provider.py::GptImageProvider.generate` (giống `generate-asset` endpoint làm), lưu asset mới, cập nhật `scene.asset_object_key`.
- Việc này chạy qua script một lần (như `build_ep1_en.py` đã dùng), không cần route API mới.

## Xử lý lỗi & kiểm thử

- Unit test cho phần A (catalog filtering) theo pattern hiện có (`tests/saas/test_script_analysis.py`), chạy `pytest` toàn bộ trước khi rebuild.
- Phần B (caption style) verify bằng render thử + trích frame thực tế (không chỉ tin vào tính toán lý thuyết — bài học từ lần trước).
- Phần C/D không có unit test (tác vụ nội dung một lần), verify bằng nghe/xem thủ công trước khi coi là xong.
- Sau khi rebuild EP 1 lần cuối: sample ít nhất 8-10 frame rải đều toàn bộ video (không chỉ đầu video) để tự kiểm tra trước khi gửi user, đúng yêu cầu "tự check lại đi thay vì cứ để tôi check".

## Ngoài phạm vi

- Composite nhiều lớp thật (background + character/object overlay chồng lên nhau) — chỉ loại asset non-location khỏi candidate pool, không xây tính năng overlay.
- Sửa lại toàn bộ 32 asset `uploaded` gốc (chỉ regenerate scene nào EP 1 thực sự dùng).
- Voice picker UI (đã có trong spec Narro Wave 2, mục 0 punch list) — ở đây chỉ chọn `voice_id` cấu hình tay cho series hiện tại.
- Quota/rate-limit AI endpoints, chuyển sync→Celery (punchlist #1/#2) — không liên quan render quality.

## Định nghĩa "xong"

- `analyze_script` không bao giờ chọn asset `character`/`object` làm nền full-frame (unit test xanh).
- Build lại EP 1 (tiếng Anh, voice mới chọn), sample 8-10 frame rải đều video — không còn cảnh crop vô nghĩa, không còn caption đè chữ có sẵn, caption dễ đọc không che quá nhiều ảnh.
- User nghe bản build cuối và xác nhận cả 3 mặt (giọng, caption, hình ảnh) đều ổn — hoặc góp ý cụ thể để lặp tiếp có kiểm soát, không đoán mò.
