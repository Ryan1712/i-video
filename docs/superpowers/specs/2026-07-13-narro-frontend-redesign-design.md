# Narro — Redesign frontend: rebrand, landing, i18n, wizard, settings

> Bổ sung cho spec v3 (`2026-07-10-product-vision-v3-design.md`). Kéo mục "landing copy + i18n" từ Phase 4 lên làm ngay theo yêu cầu chủ dự án (2026-07-13), gộp thêm voice picker (punch list mục 0) và mở rộng: wizard chạy agent + Settings hub. Backend pipeline AI không đổi.

## Quyết định đã chốt (2026-07-13)

1. **Tên sản phẩm: Narro** (từ "narrate"). Thay toàn bộ branding "What If?" ở landing, auth, dashboard. "What If: Zombie Apocalypse" chỉ còn là TÊN MỘT SERIES của chủ dự án, không phải tên app.
2. **Định vị** (giữ từ spec v3): bán "biến một ý tưởng thành cả series video nhất quán" — nhân vật, giọng, phong cách giữ nguyên xuyên tập. Copy landing chỉ hứa tính năng ĐÃ CHẠY: AI viết kịch bản đúng thời lượng (user duyệt), chia cảnh + khớp ảnh từ kho series, sinh ảnh thiếu, TTS đa ngôn ngữ, phụ đề, dựng video, upload YouTube. KHÔNG nhắc timeline editor (Phase 3 chưa xây).
3. **i18n ngay bây giờ**: song ngữ EN/VI bằng **next-intl** (routing `/en` `/vi`, hỗ trợ App Router + server components, SEO cho landing) — thay cho react-i18next ghi trong spec v3 (client-only, kém SEO). Chuỗi UI trong `messages/en.json` + `messages/vi.json`. Switcher ở Nav landing + sidebar dashboard. Locale mặc định: `en`.
4. **Trải nghiệm chạy agent: wizard từng bước có duyệt** là mặc định; chế độ auto-pilot một nút để chỗ sẵn trong thiết kế nhưng XÂY SAU khi wizard chạy ổn (ngoài phạm vi 2 wave này).
5. **Thực thi 2 wave**: Wave 1 = rebrand + i18n + landing. Wave 2 = wizard + Settings hub + voice picker. Mỗi wave một plan riêng; EP 2-3 có thể chen giữa hai wave.

## Wave 1 — Danh tính (rebrand + i18n + landing)

### Rebrand
- Logo: chữ "N" trong khối gradient indigo (giữ palette `#6366F1 → #818CF8` hiện tại), wordmark "Narro". Đổi tại: `components/landing/Nav.tsx`, `Footer.tsx`, `app/dashboard/layout.tsx` (sidebar), `app/layout.tsx` (title/metadata), favicon.
- Theme tối indigo hiện tại GIỮ NGUYÊN — chỉ đổi nội dung, không đại tu visual.

### i18n (next-intl)
- Cấu trúc: `frontend/src/app/[locale]/...` (di trú `(auth)`, `dashboard`, landing page vào segment `[locale]`), middleware next-intl cho locale detection + redirect `/` → `/en`.
- `messages/en.json`, `messages/vi.json` — phủ: landing, auth, dashboard chrome (sidebar, nút chung), series/episodes pages, thông báo lỗi frontend (map từ `ERR_...`).
- Switcher: dropdown EN/VI ở Nav (landing) và cuối sidebar (dashboard); lưu lựa chọn qua cookie next-intl mặc định.
- Định nghĩa xong: đổi locale thì TOÀN BỘ chuỗi nhìn thấy đổi theo; không còn chuỗi hardcode trong component đã di trú.

### Landing mới (giữ khung 7 section, viết lại ruột)
1. **Nav**: logo Narro, links Features / How it works / Pricing, switcher ngôn ngữ, Login / Get started.
2. **Hero**: H1 "Turn one idea into a whole series" / "Biến một ý tưởng thành cả series video". Sub: AI viết kịch bản — bạn duyệt — Narro dựng video và đăng YouTube, nhân vật + giọng đọc nhất quán mọi tập. CTA "Start your series". Visual: screenshot wizard thật (chụp sau khi Wave 2 xong; tạm thời dùng screenshot trang episode hiện tại).
3. **How it works — 4 bước đúng pipeline thật**: (1) Nhập ý tưởng + thời lượng → (2) AI viết kịch bản, bạn biên tập → (3) Tự chia cảnh, khớp ảnh kho series, sinh ảnh thiếu → (4) Video hoàn chỉnh + phụ đề + giọng đọc, đăng thẳng YouTube.
4. **Features 6 cards**: Script-to-length AI · Series asset library (nhất quán nhân vật) · AI image generation theo style bible · TTS đa ngôn ngữ (VI/EN) · Phụ đề chính xác 100% từ kịch bản · One-click YouTube publish.
5. **Pricing**: giữ cấu trúc plans hiện tại, chỉ i18n hóa chuỗi.
6. **CTA + Footer**: Narro, links, bản quyền.
- Stats giả trong Hero hiện tại ("10× faster", "100% AI-powered") THAY bằng 3 fact thật của pipeline (ví dụ: "1 ý tưởng → kịch bản 8 phút", "34/37 cảnh tự khớp ảnh", "VI + EN") — số liệu minh họa được phép ghi chú "from our pilot episode".

## Wave 2 — Trải nghiệm (wizard + settings + voice picker)

### Wizard chạy agent (trang episode)
- Trang `dashboard/episodes/[id]` chuyển thành **stepper 5 bước**: Ý tưởng → Kịch bản → Cảnh & Ảnh → Build → Xuất bản.
- Bước hiện tại SUY RA từ dữ liệu episode (không lưu state riêng): `script == ""` → bước 1; có script, `scenes == []` → bước 2; có scenes, thiếu ảnh hoặc `status == draft` → bước 3; `status ∈ {building}` → bước 4; `built/uploading/uploaded` → bước 5. User quay lại bước trước được (sửa kịch bản → re-analyze, có cảnh báo "sẽ thay toàn bộ cảnh").
- Mỗi bước một component riêng trong `components/episode/steps/`: `IdeaStep`, `ScriptStep` (textarea + word count + ước phút), `ScenesStep` (danh sách cảnh, thumbnail ảnh khớp qua presigned URL, nút sinh ảnh/upload từng cảnh, đếm "x/y cảnh có ảnh"), `BuildStep` (progress + lỗi job), `PublishStep` (download + YouTube).
- Trạng thái agent hiển thị rõ: spinner + label ("Agent đang viết kịch bản…", "Đang chia cảnh…"), disable điều hướng khi đang gọi AI.
- Chỗ sẵn cho auto-pilot: nút "⚡ Auto-pilot" trong header wizard, Wave 2 chỉ render `disabled` + tooltip "coming soon".

### Settings hub
- Sidebar gọn: **Series · Episodes · Settings** (YouTube/Billing rời sidebar, thành tab trong Settings).
- Route `dashboard/settings` với 4 tab:
  1. **Account**: email (hiển thị), đổi mật khẩu (mật khẩu cũ + mới ×2), nút xóa tài khoản (confirm bằng gõ email; backend: xóa user + cascade series/episodes/assets — soft-delete KHÔNG cần ở bước này).
  2. **Defaults**: ngôn ngữ mặc định, giọng đọc mặc định (voice picker), thời lượng mặc định (phút), caption style. Lưu `users.preferences` jsonb. Form tạo series/episode mới prefill từ preferences.
  3. **YouTube**: di trú nguyên trang hiện có thành tab.
  4. **Billing**: di trú nguyên trang hiện có thành tab.

### Voice picker (dùng chung: Settings Defaults + form series)
- Component `VoicePicker`: dropdown giọng theo provider + ngôn ngữ, mỗi option có tên + giới tính/tag, nút ▶ nghe thử (phát mẫu ~5s).
- Backend `GET /voices?provider=&language=`: ElevenLabs → proxy `GET /v1/voices` (nếu key thiếu quyền voices_read thì fallback danh sách voice ID đã cấu hình + premade tĩnh); Azure → danh sách tĩnh trong code (vi-VN/en-US neural). Cache in-memory 1 giờ. Nghe thử: `POST /voices/preview` {provider, voice, language} → audio bytes (giới hạn text mẫu cố định server-side, chống lạm dụng credits).
- Series form thay ô text `voice_id` bằng `VoicePicker`; giữ ô "Custom voice ID" nhỏ cho power user.

### Backend mới (Wave 2, đều nhỏ)
- `PUT /series/{series_id}`: sửa name/description/style (owner-scoped 404).
- `POST /auth/change-password`: old + new, verify hash cũ, `ERR_WRONG_PASSWORD` 400.
- `DELETE /auth/me`: xóa tài khoản + dữ liệu (confirm phía client).
- `GET /me/preferences` / `PUT /me/preferences`: cột mới `users.preferences` jsonb default `{}` (ALTER tay như quy ước).
- `GET /voices`, `POST /voices/preview` như trên. Preview gọi TTS provider thật → tốn credit ít (câu mẫu ngắn cố định); rate-limit đơn giản: tối đa 20 preview/user/giờ (in-memory).

## Xử lý lỗi & kiểm thử
- Mọi chuỗi lỗi hiển thị qua map i18n từ mã `ERR_...` (mở rộng pattern `ERROR_MESSAGES` hiện có, chuyển vào messages json).
- Jest: test render landing (2 locale), switcher đổi chuỗi, wizard suy bước đúng từ 5 trạng thái episode dữ liệu giả, settings tabs, VoicePicker (mock /voices). Backend: pytest cho 5 endpoint mới theo pattern hiện hành (SQLite + monkeypatch, không gọi API thật).
- Playwright E2E hiện có: cập nhật selector theo branding mới trong cùng wave (không để test đỏ qua đêm).

## Ngoài phạm vi (nói rõ để khỏi trôi)
- Auto-pilot một nút (xây sau khi wizard ổn định).
- BYOK (user tự nhập API key).
- Timeline editor (Phase 3 spec v3), Remotion (Phase 2).
- Đổi theme/visual system, trang admin.
- Nội dung landing tiếng thứ 3.

## Định nghĩa "xong"
- **Wave 1**: mở `/vi` và `/en` thấy landing Narro hoàn chỉnh đúng định vị, không còn chữ "What If?" ở bất kỳ đâu ngoài tên series demo; switcher hoạt động cả landing lẫn dashboard; Jest + Playwright xanh.
- **Wave 2**: làm một episode mới từ đầu đến build CHỈ qua wizard; đổi mật khẩu + set defaults + chọn giọng có nghe thử qua Settings; tạo series mới prefill defaults và chọn giọng bằng VoicePicker.
