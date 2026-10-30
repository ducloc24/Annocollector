# Từ điển thuật ngữ

> Mục đích: thống nhất cách gọi trong docs, code và giao diện. Khi một từ có hai
> nghĩa thì ghi rõ nghĩa nào được dùng ở đây.
>
> Liên quan: `docs/prd.md`, `docs/role_in_system.md`, `docs/review_workflow.md`.
> Trạng thái: draft, cập nhật khi chốt thêm khái niệm.

---

## 0. Quy ước đặt tên (theo CVAT)

Tên các cấp công việc đi theo CVAT. Hai từ dễ nhầm nhất:

| Từ | Nghĩa trong hệ thống này | Lưu ý |
| --- | --- | --- |
| **Task** | Một gói dữ liệu của project, do PO nghiệm thu | Trước đây gọi là `batch` |
| **Job** | Đơn vị giao cho annotator làm và review | Trước đây gọi là `task` |

Thứ bậc: `Project → Task → Job → Item`

- Một project có nhiều task.
- Một task được cắt thành nhiều job.
- Một job chứa nhiều item.

---

## 1. Dữ liệu và công việc

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **Project** | Một dự án gán nhãn do PO tạo. Có dataset, guideline, thành viên và cấu hình riêng. |
| **Dataset** | Dữ liệu thô PO upload lên project. |
| **Dataset version** | Một phiên bản dataset, bất biến. Đổi dữ liệu thì tạo version mới. Mẫu số của tiến độ tính theo version này. |
| **Item** | Đơn vị nhỏ nhất cần gán nhãn. Ví dụ: một tool call trong trajectory, một ảnh, một câu. |
| **Item type** | Loại item (trajectory, ảnh, text...). Mỗi loại có parser và cách hiển thị riêng trong code. |
| **Item type registry** | Danh sách các item type đăng ký trong code, ở cả backend (parser, validator) và frontend (renderer, công cụ gán nhãn). Thêm loại mới là thêm một mục vào registry, không sửa phần lõi. |
| **Renderer** | Component frontend hiển thị một item của một item type (trajectory viewer, ảnh, audio). |
| **Công cụ gán nhãn (annotation tool)** | Phần giao diện cho annotator nhập nhãn trên item: form chọn nhãn, canvas vẽ box, bôi span. Nặng nhất với loại cần vẽ. |
| **Task** | Gói dữ liệu của một project mà PO nghiệm thu. Được cắt thành nhiều job. |
| **Job** | Gói item cố định, thuộc một task, giao cho một annotator làm và được review như một đơn vị. Ghim vào một guideline version và một job config. |
| **Job config** | Cấu hình do PO đặt, quy định thế nào là một job: số item mỗi job, số annotator, tỷ lệ review, SLA, label schema. Có version, bất biến. |
| **Pin / ghim** | Gắn một job vào đúng version guideline và job config tại lúc giao, để về sau chấm theo đúng căn cứ lúc làm. |
| **Đội đánh giá (team)** | Nhóm annotator và reviewer do HR lập. PO chọn đội cho project và giao task cho đội; thành viên đội tự lấy việc trong task của đội. |
| **Team role** | Vai trò của một người trong một đội: `annotator` hoặc `reviewer`. Mỗi người một vai trò trong một đội. |
| **Gắn đội (project team)** | Liên kết một đội với một project (`project_teams`); thành viên đội có quyền trong project theo team role. |
| **Trưởng nhóm (team lead)** | Thành viên đội được HR bật cờ `is_lead`. Vẫn làm việc như annotator hoặc reviewer; thêm quyền xem số liệu tải, tiến độ, chất lượng của đội và nhận cảnh báo. Không xem nội dung job không được giao, không xem đáp án gold, không sửa danh sách đội. |
| **Push (giao việc)** | Người điều phối (PM) chọn job và giao cho từng người. |
| **Pull (nhận việc)** | Người làm bấm "lấy việc tiếp theo", hệ thống chọn job cho họ theo quy tắc. Người làm không tự chọn job cụ thể. |
| **Cherry-picking** | Người làm tự chọn job dễ, bỏ job khó. Lý do không cho annotator duyệt pool để chọn. |
| **WIP limit** | Số job tối đa một người được giữ đang mở cùng lúc. |
| **`SKIP LOCKED`** | Cơ chế của Postgres cho nhiều người lấy việc cùng lúc mà không lấy trùng một job. |
| **Pool** | Hàng đợi job chưa có người làm. Job của người đã nghỉ quay về đây. |
| **Lease** | Thời hạn một annotator được giữ job (`lease_expires_at`). Hết hạn mà chưa xong thì job có thể bị thu hồi. |

## 2. Gán nhãn

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **Submission** | Một lần annotator nộp bài cho một job. Mỗi lần bị reject rồi làm lại là một submission mới, nên giữ được lịch sử các vòng. |
| **Round** | Số thứ tự vòng nộp của một job (1, 2, 3...). |
| **Supersedes** | Quan hệ "thay thế": một review mới (override, re-review) trỏ về review cũ mà nó thay thế, không sửa bản cũ. |
| **Gold answer** | Đáp án chuẩn của một item trong gold job, dùng để đo chất lượng. Chỉ vai trò chấm chất lượng đọc được. |
| **Target** | Phần cụ thể trong một item được gán nhãn, ví dụ id của một bước tool call trong trajectory. Nhãn gắn vào cặp `(item_id, target)`; để trống khi nhãn cho cả item. |
| **Annotation** | Kết quả gán nhãn của annotator cho các item trong một job, lưu dạng `annotation_json`. |
| **Label** | Nhãn gán cho một item. |
| **Label schema** | Mô tả (JSON) các trường nhãn: tên, kiểu, bắt buộc hay không, điều kiện hiện. Từ đó dựng form gán nhãn và validate kết quả. |
| **Guideline** | Tài liệu quy tắc gán nhãn do PO viết cho project. Là căn cứ duy nhất để chấm. |
| **Guideline version** | Một phiên bản guideline, bất biến. |
| **Self-check** | Bước annotator tự soát trước khi submit. Không phải review chính thức. |
| **Trajectory** | Một lượt chạy của agent: yêu cầu của user, các bước suy nghĩ, tool call, tool result và câu trả lời cuối. |
| **Tool call** | Một lần agent gọi tool, gồm tên tool và tham số. Là item trong bài toán đánh giá agent. |
| **Tool result** | Kết quả tool trả về cho một tool call. |
| **Verdict** | Kết luận của annotator cho một tool call: `correct`, `incorrect` hoặc `unsure`. |
| **Reason code** | Mã lý do khi `incorrect` hoặc khi reviewer reject, ví dụ `WRONG_TOOL`, `WRONG_ARGS`, `MISSING_ARG`, `HALLUCINATED_ARG`, `UNNECESSARY_CALL`, `WRONG_ORDER`, `IGNORED_RESULT`. |
| **Unsure** | Verdict "không chắc". Job có item unsure được đẩy lên đầu queue review. |

### Các loại annotation

Mỗi loại khác nhau ở parser, cách hiển thị item và công cụ gán nhãn. Phần job,
review, tiến độ và phân quyền dùng chung.

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **Tool-call review** | Đánh giá từng tool call trong trajectory là đúng hay sai. Loại ưu tiên làm đầu tiên. |
| **Trajectory evaluation** | Đánh giá cả trajectory: hoàn thành mục tiêu chưa, có lòng vòng hoặc hành động nguy hiểm không. |
| **Process reward** | Đánh giá từng bước suy luận của agent là hợp lý, sai hay vô ích. |
| **Preference (A/B)** | So sánh hai câu trả lời cho cùng prompt, chọn câu tốt hơn hoặc hoà. Dùng cho RLHF. |
| **Rating / chấm điểm** | Cho điểm một câu trả lời theo thang hoặc theo từng tiêu chí (đúng sự thật, đầy đủ, văn phong). |
| **Fact-checking** | Kiểm tra một khẳng định có căn cứ, bịa, hay không kiểm chứng được. |
| **Hallucination** | Model đưa ra thông tin hoặc tham số không có trong ngữ cảnh. |
| **Red-team** | Thử và gán nhãn các lượt hội thoại có nguy cơ vi phạm chính sách an toàn. |
| **RLHF** | Học tăng cường từ phản hồi của con người; dữ liệu preference và rating thường phục vụ việc này. |
| **Text classification** | Chọn nhãn cho cả một đoạn text (cảm xúc, chủ đề, ý định). |
| **NER (nhận diện thực thể)** | Bôi một đoạn text và gán loại thực thể (người, địa điểm, tổ chức). |
| **Span** | Một đoạn text liên tục được bôi để gán nhãn. |
| **Relation extraction** | Nối hai thực thể và gán loại quan hệ giữa chúng. |
| **Object detection** | Vẽ bounding box quanh đối tượng trong ảnh và gán lớp. |
| **Bounding box** | Hình chữ nhật bao quanh một đối tượng. |
| **Segmentation** | Vẽ polygon hoặc mask theo đúng hình dạng đối tượng. |
| **Keypoint** | Đánh dấu các điểm đặc trưng (khớp người, mốc khuôn mặt). |
| **Tracking** | Theo dõi một đối tượng qua nhiều frame video. |
| **Transcription** | Gõ lại nội dung audio thành văn bản. |
| **Form engine** | Thành phần dựng form gán nhãn từ label schema. Đủ cho các loại chỉ chọn nhãn, không đủ cho loại cần canvas. |

### Parser và định dạng dữ liệu

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **Parser** | Thành phần đọc dữ liệu thô PO upload, kiểm tra định dạng và chuyển thành item. Mỗi `item_type` có parser riêng. |
| **Parser registry** | Danh sách parser đã đăng ký trong code theo tên. Cấu hình trong DB chỉ trỏ tới tên parser, không chứa code. |
| **Field mapping** | Bản đồ khai báo "trường nào trong dữ liệu thô là gì" (dạng JSONPath), cho phép một parser tổng quát đọc nhiều định dạng JSON khác nhau mà không cần viết code mới. |
| **JSONPath** | Cú pháp trỏ tới một trường trong JSON, ví dụ `$.messages[*].tool_calls[*]`. |
| **`parser_version`** | Phiên bản parser đã dùng để đọc một dataset version, để biết dữ liệu được đọc bằng bản nào. |
| **JSONL** | File mỗi dòng là một bản ghi JSON. Phổ biến nhất với dữ liệu LLM. |
| **Parquet** | Định dạng bảng nhị phân cho dữ liệu lớn, hay gặp khi lấy dataset từ Hugging Face. |
| **Chat messages** | Dữ liệu hội thoại dạng danh sách message có `role` (user, assistant, tool); tool call nằm trong message của assistant. |
| **Agent trace** | Log một lượt chạy của agent từ framework (LangChain, LlamaIndex...) hoặc tự viết: các bước, tool call, kết quả. |
| **OpenTelemetry trace** | Dữ liệu theo dõi chuẩn gồm các span lồng nhau, có thể dùng làm nguồn trajectory. |
| **COCO** | Định dạng JSON cho object detection và segmentation. |
| **Pascal VOC** | Định dạng XML cho bounding box. |
| **YOLO** | Định dạng txt cho bounding box. |
| **CoNLL / IOB** | Định dạng nhãn cho NER, mỗi token một nhãn. |
| **Pre-annotation** | Nhãn có sẵn (từ model hoặc hệ thống cũ) nhập vào để annotator chỉ sửa thay vì làm từ đầu. |
| **Checksum** | Giá trị băm của file dataset, dùng để xác nhận dữ liệu không bị đổi. |

## 3. Review và chất lượng

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **Review / QC** | Chấm job đã submit theo rubric, ra quyết định accept, accept_with_fix hoặc reject. |
| **Rubric** | Bảng tiêu chí chấm, thống nhất trước khi project bắt đầu. |
| **Calibration** | Buổi các reviewer chấm thử và thống nhất cách chấm trước khi review thật. |
| **Accept** | Job đạt, đưa vào dataset. |
| **Accept with fix** | Job hợp lệ như accept, còn lỗi nhỏ. Vẫn vào dataset nhưng ghi lỗi vào hồ sơ chất lượng. |
| **Reject** | Job lỗi lớn, trả về để annotator sửa. Phải có lý do. |
| **Rework** | Lần annotator sửa lại sau khi bị reject. Tối đa 2 lần (cấu hình được). |
| **Escalate** | Chuyển lên PM hoặc PO quyết khi reviewer không chắc, có tranh chấp, hoặc quá số lần rework. |
| **Appeal** | Annotator không đồng ý quyết định reject và mở khiếu nại. PM xử lý bước 1, PO quyết cuối. |
| **Override** | PO đổi quyết định của reviewer. Bắt buộc có lý do và ghi audit. |
| **Re-review** | Review lại một job hoặc task đã accept. Tạo bản ghi mới, không mở lại job cũ. |
| **Correction** | Sửa nhãn trực tiếp. Chỉ khi bắt buộc, có quyền riêng và audit riêng. |
| **Consensus** | Nhiều annotator cùng làm một job để so sánh kết quả. Chưa chốt có dùng không. |
| **IAA (inter-annotator agreement)** | Mức đồng thuận giữa các annotator cùng làm một job. Đo bằng kappa; ngưỡng gợi ý ≥ 0.7. |
| **Kappa (Cohen's / Fleiss')** | Chỉ số đồng thuận đã trừ phần trùng do ngẫu nhiên. Cohen's cho hai người, Fleiss' cho từ ba người trở lên. |
| **Adjudicator** | Người chốt kết quả cuối khi các annotator hoặc reviewer lệch nhau (consensus). Kết quả là một bản ghi `adjudicated` có `decided_by`. |
| **Double review** | Cho reviewer thứ hai chấm độc lập một mẫu ngẫu nhiên job reviewer đầu đã accept, để kiểm tra chính reviewer. |
| **Golden example** | Ví dụ đúng/sai mẫu cho từng tiêu chí trong rubric. |
| **Coaching** | Buổi hướng dẫn khi annotator lặp lại cùng một `reason_code`, thay cho chỉ trừ điểm. |
| **Auto-accept** | Job không được chọn vào mẫu review (khi `review_rate` < 1) nên tự chuyển `accepted`, kèm một dòng review `auto_accept` không có reviewer. |
| **Coaching flag** | Cờ "nên kèm cặp" trên trang trưởng nhóm: một annotator bị ghi cùng một mã lỗi từ hai lần trở lên. |
| **Gold job** | Job đã có đáp án chuẩn, trộn vào hàng đợi để đo chất lượng và phát hiện gian lận. Không để lộ cho annotator. |
| **Sampling / lấy mẫu** | Chỉ review một phần job thay vì 100%, chọn ngẫu nhiên. |
| **Acceptance / nghiệm thu** | PO duyệt cả task: kiểm tra tỷ lệ pass, lỗi lặp, mẫu ngẫu nhiên 5–10%. |
| **Sign-off** | PO ký nghiệm thu; task chuyển `delivered`. |
| **Delivered** | Trạng thái task sau khi PO ký nghiệm thu, sẵn sàng giao stakeholder. |

## 4. Trạng thái job

| Trạng thái | Ý nghĩa |
| --- | --- |
| `unassigned` | Trong pool, chưa có người nhận |
| `assigned` | Đã giao cho annotator, chưa bắt đầu |
| `in_progress` | Annotator đang làm |
| `submitted` | Annotator đã nộp (sau self-check) |
| `in_review` | Đang trong queue hoặc đang được reviewer chấm |
| `accepted` | Đạt, điểm kết thúc của job |
| `accepted_with_fix` | Đạt với lỗi nhỏ, điểm kết thúc |
| `rejected` | Lỗi lớn, chờ annotator sửa |
| `escalated` | Chuyển lên PM hoặc PO quyết |

Tiến độ chỉ đếm job `accepted`, không đếm `submitted`.

## 5. Vai trò và phân quyền

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **Platform role** | Năng lực toàn hệ thống, do HR cấp. Quyết định một người **được phép** làm vai nào. |
| **RBAC** | Phân quyền theo vai trò: user có role, role có permission; code kiểm tra permission chứ không kiểm tra tên role. |
| **Permission** | Một quyền thực hiện một hành động trên một loại tài nguyên, đặt tên `resource.action` (ví dụ `job.review`). |
| **Limit** | Phạm vi dữ liệu của một permission trong một role: `all` (toàn hệ thống), `P` (project mình thuộc), `A` (chỉ job được giao), `own` (của chính mình). |
| **Role requirement** | Khai báo role project nào đòi role platform nào (ví dụ project `reviewer` cần platform `reviewer`). |
| **Role conflict** | Cặp role không được đi cùng nhau (chặn) hoặc chỉ cảnh báo, ví dụ annotator và reviewer cùng project. |
| **Separation of duties (tách trách nhiệm)** | Nguyên tắc không để một người nắm hai vai làm mất tính độc lập. Hiện thực bằng role conflict và quy tắc ở service. |
| **ABAC** | Phân quyền theo thuộc tính (mức dữ liệu, giờ làm...). Chỉ cần nếu RBAC không đủ biểu diễn. |
| **Project role** | Vai trò trong một project cụ thể, do PO cấp. Quyết định một người **được làm** gì trong project đó. |
| **Project member** | Bản ghi gán một user vào một project với một project role. |
| **PO** | Product Owner: tạo project, upload dataset, viết guideline, cấu hình job config, nghiệm thu task. |
| **Annotator** | Người gán nhãn. |
| **Reviewer** | Người chấm job. Không review job của chính mình. |
| **PM (project manager)** | Điều phối job, cân tải, theo dõi tiến độ, xử lý tranh chấp bước 1. |
| **HR admin** | Tạo tài khoản, cấp và thu hồi platform role. Không xem được dataset. |
| **Platform admin** | Cấu hình và vận hành hệ thống. Không cấp quyền nghiệp vụ. |
| **Auditor** | Đọc audit log và báo cáo tuân thủ. Chỉ đọc. |
| **Owner / Manager / Viewer** | Project role: toàn quyền trong project / điều phối / chỉ đọc tiến độ và báo cáo. |
| **Service account** | Tài khoản của bot hoặc cron job, do platform admin tạo, tách khỏi tài khoản người. |
| **JWT** | Token đăng nhập tự chứa thông tin (user, hạn dùng), có chữ ký. Server kiểm tra chữ ký mà không cần tra DB. |
| **Access token** | JWT ngắn hạn gửi kèm mỗi request để xác thực. |
| **Refresh token** | Token dài hạn dùng để xin access token mới; lưu trong DB nên thu hồi được. |
| **`token_version`** | Số đếm trên user; tăng lên thì mọi access token cũ của user đó mất hiệu lực. |
| **Xoay vòng refresh token (rotation)** | Mỗi lần refresh cấp token mới và thu hồi token cũ. Các token nối tiếp nhau thuộc một **family**; dùng lại token đã bị thay thế thì thu hồi cả family. |
| **Action token** | Token dùng một lần gửi qua email để kích hoạt tài khoản hoặc đặt lại mật khẩu (`user_action_tokens`). |
| **Break-glass** | Truy cập dataset khẩn cấp ngoài quyền thường, bắt buộc có lý do và ghi audit. |
| **`expires_at`** | Thời điểm quyền hết hiệu lực. Để trống nghĩa là vô thời hạn. |
| **Onboarding** | HR tạo user và cấp platform role; PO add user vào project. |
| **Offboarding** | HR disable user: thu hồi toàn bộ quyền, vô hiệu membership, huỷ session, trả job dở về pool. |
| **Xung đột lợi ích** | Tình huống một người nắm hai vai làm mất tính độc lập, ví dụ annotator kiêm reviewer cùng project. Bị chặn ở tầng API. |

## 6. Tiến độ và vận hành

| Thuật ngữ | Định nghĩa |
| --- | --- |
| **% hoàn thành** | Job `accepted` / tổng job của dataset version. |
| **Throughput** | Số job accepted mỗi ngày, theo annotator và theo project. |
| **Backlog** | Job chưa có người làm cộng job đang chờ review. |
| **Cycle time** | Thời gian trung bình từ lúc giao đến khi accepted. |
| **Stuck** | Job nằm quá SLA ở một trạng thái. Cảnh báo gửi cho PM. |
| **SLA** | Thời hạn xử lý tối đa cho từng bước (làm, review, nghiệm thu). |
| **Action endpoint** | Endpoint thực hiện một hành động đổi trạng thái (`POST /jobs/{id}/submit`) thay vì sửa trực tiếp trường `status`. |
| **`unassigned`** | Trạng thái job trong pool, chưa có người nhận. |
| **Workspace project** | Trang `/projects/[id]` gom mọi thứ của một project (dữ liệu, cấu hình, task, job, tiến độ) theo tab; tab hiện theo vai trò. |
| **Checklist thiết lập** | Danh sách bước PO cần làm để project chạy được: guideline, đội, dữ liệu, cấu hình job, task, kích hoạt. |
| **Màn làm việc** | Màn gán nhãn hoặc màn chấm, chiếm toàn trang, không có menu. |
| **State machine** | Module duy nhất định nghĩa các trạng thái và chuyển hợp lệ của job hoặc task. Mọi đổi trạng thái đi qua đây. |
| **Permission resolver** | Thành phần backend trả lời "user này có permission này trên project này không", theo đúng thứ tự kiểm tra quyền. |
| **Seed** | Dữ liệu khởi tạo đưa vào DB qua migration, ví dụ danh mục role, permission và ma trận quyền. |
| **Storage adapter** | Lớp trung gian lưu và đọc file (ổ đĩa cục bộ, Supabase Storage, S3) để đổi nơi lưu mà không sửa nghiệp vụ. |
| **R2** | Dịch vụ lưu file của Cloudflare, tương thích S3 API. Dùng để lưu file dataset gốc. |
| **Presigned URL** | Link tạm thời có chữ ký, cho phép tải lên hoặc tải về một file cụ thể trong thời gian ngắn mà không cần mở bucket công khai. |
| **Draft (bản nháp)** | Nhãn annotator đang làm dở, tự lưu, chưa nộp. Khác với submission. |
| **Tác vụ nền (background task)** | Tác vụ chạy định kỳ hoặc ngoài request: trả job hết lease về pool, cảnh báo stuck, parse file lớn. |
| **Audit log / `audit_events`** | Nhật ký append-only mọi hành động quan trọng: ai, làm gì, trên đối tượng nào, trước và sau, lý do. |
| **Append-only** | Chỉ thêm bản ghi, không sửa hay xoá. Áp dụng cho audit log, dataset version, guideline version, job config. |
| **Data classification** | Mức phân loại dữ liệu của project (`internal`, `confidential`, `restricted`). |

---

## Ghi chú về phạm vi

Nền tảng chỉ làm thu thập và gán nhãn. Không có trạng thái thanh toán, không tính
tiền cho annotator, không quy đổi job ra tiền tệ.
