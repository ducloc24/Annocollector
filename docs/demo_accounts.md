# Tài khoản demo

> Chỉ dùng để trình diễn trên môi trường demo. Mật khẩu nằm trong file này nên **không dùng
> cho dữ liệu thật** và nên đổi (hoặc xoá tài khoản) trước khi đưa repo ra ngoài.

Mật khẩu chung cho mọi tài khoản bên dưới: `Demo#Vungroip2026`

| Email | Vai trò (platform role) | Dùng để demo |
| --- | --- | --- |
| `hr@vungroip.tech` | `hr_admin` | Tạo người dùng, cấp và thu hồi role, lập đội đánh giá, offboarding, quyền sắp hết hạn, audit về quyền |
| `po@vungroip.tech` | `po` | Tạo project, viết guideline, upload dữ liệu, cấu hình job, tạo task, gắn đội, nghiệm thu, đổi quyết định, export |
| `pm@vungroip.tech` | `project_manager` | Điều phối job, giao tay, theo dõi tiến độ, xử lý escalation và khiếu nại |
| `annotator1@vungroip.tech` | `annotator` | Lấy việc, gán nhãn, nộp, khiếu nại khi bị trả lại |
| `annotator2@vungroip.tech` | `annotator` | Như trên (người thứ hai, để thấy hai người lấy việc không trùng nhau) |
| `reviewer1@vungroip.tech` | `reviewer` | Lấy việc chấm, ghi lỗi, trả lại hoặc chấp nhận |
| `reviewer2@vungroip.tech` | `reviewer` | Như trên (người thứ hai) |
| `admin@vungroip.tech` | `platform_admin` | Trang Hệ thống (cài đặt vận hành) |
| `auditor@vungroip.tech` | `auditor` | Đọc audit log và ma trận quyền, chỉ đọc |

Tài khoản cũ `konan.yukata.1947@gmail.com` (`hr_admin`) và dữ liệu thử do kiểm thử tự động tạo
(các user `smoke-*`, `e2e-*`, project và đội thử) vẫn còn trong DB.

## Kịch bản demo gợi ý

Các tài khoản mới chưa thuộc đội hay project nào. Đi theo thứ tự này để thấy trọn vòng:

1. **HR** (`hr@`): Đội đánh giá → Tạo đội → thêm `annotator1`, `annotator2` (vai trò annotator) và
   `reviewer1`, `reviewer2` (vai trò reviewer). Chỉ định một người làm trưởng nhóm nếu muốn.
2. **PO** (`po@`): Project → Tạo project. Làm theo checklist ở tab Tổng quan:
   guideline → gắn đội → upload dữ liệu (`be/samples/trajectories.jsonl`) → cấu hình job
   → tạo task → kích hoạt project và task.
3. **Annotator** (`annotator1@`, `annotator2@`): Gán nhãn → Lấy việc tiếp theo → gán nhãn từng
   tool call → tick self-check → Nộp.
4. **Reviewer** (`reviewer1@`): Chấm → Lấy việc chấm → ghi lỗi → Trả lại (hoặc Chấp nhận).
5. **Annotator**: thấy job bị trả lại, sửa và nộp lại, hoặc Khiếu nại.
6. **PM** (`pm@`) cần được PO thêm vào project (tab Thành viên và đội) trước khi thấy project;
   sau đó xem Job, Escalation, Khiếu nại.
7. **PO**: Chi tiết task → Ký nghiệm thu → Export JSONL; tab Chất lượng.
8. **Admin** (`admin@`): Hệ thống. **Auditor** (`auditor@`): Audit.

## Chạy hệ thống

```
npm run dev      # API :8000, web :3000
```

Mở http://localhost:3000 và đăng nhập. Tài khoản `pm@`, `auditor@` chỉ thấy project khi được
thêm vào project; `po@` chỉ thấy project do mình tạo hoặc được thêm vào.

## Dọn dẹp

Xoá các tài khoản này khi không còn demo: HR vào Người dùng → chọn người → Vô hiệu hoá. Hệ thống
không xoá cứng người dùng, tài khoản chỉ chuyển sang trạng thái "đã nghỉ" và mất mọi quyền.
