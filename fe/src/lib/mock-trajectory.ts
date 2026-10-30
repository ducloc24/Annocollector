// Demo data for the annotation screen preview. Not wired to the backend.

export type Verdict = "correct" | "incorrect" | "unsure";

export const REASON_CODES = [
  { code: "WRONG_TOOL", label: "Chọn sai tool" },
  { code: "WRONG_ARGS", label: "Sai giá trị tham số" },
  { code: "MISSING_ARG", label: "Thiếu tham số bắt buộc" },
  { code: "HALLUCINATED_ARG", label: "Tham số bịa, không có trong ngữ cảnh" },
  { code: "UNNECESSARY_CALL", label: "Gọi thừa" },
  { code: "WRONG_ORDER", label: "Sai thứ tự" },
  { code: "IGNORED_RESULT", label: "Bỏ qua kết quả trước đó" },
] as const;

export type ToolSchema = {
  name: string;
  description: string;
  params: { name: string; type: string; required: boolean }[];
};

export type Step =
  | { id: string; type: "user"; content: string }
  | { id: string; type: "thought"; content: string }
  | {
      id: string;
      type: "tool_call";
      tool: string;
      args: Record<string, unknown>;
    }
  | { id: string; type: "tool_result"; content: string; isError?: boolean }
  | { id: string; type: "assistant"; content: string };

export type DemoJob = {
  id: string;
  project: string;
  guidelineVersion: string;
  guideline: string[];
  tools: ToolSchema[];
  steps: Step[];
};

export const DEMO_JOB: DemoJob = {
  id: "JOB-0142",
  project: "Agent tool-call review",
  guidelineVersion: "v3",
  guideline: [
    "Đúng tool: tool được chọn phải phù hợp với mục tiêu của bước đó.",
    "Đúng tham số: đủ tham số bắt buộc, giá trị lấy từ yêu cầu của user hoặc kết quả trước, không bịa.",
    "Đúng thời điểm: không gọi thừa, không gọi trước khi có đủ thông tin.",
    "Nếu không chắc, chọn Unsure và ghi chú để reviewer xem trước.",
  ],
  tools: [
    {
      name: "search_flights",
      description: "Tìm chuyến bay theo tuyến và ngày.",
      params: [
        { name: "origin", type: "string (IATA)", required: true },
        { name: "destination", type: "string (IATA)", required: true },
        { name: "date", type: "string (YYYY-MM-DD)", required: true },
      ],
    },
    {
      name: "book_flight",
      description: "Đặt một chuyến bay đã tìm được.",
      params: [
        { name: "flight_id", type: "string", required: true },
        { name: "passenger_name", type: "string", required: true },
      ],
    },
    {
      name: "send_email",
      description: "Gửi email cho user.",
      params: [
        { name: "to", type: "string", required: true },
        { name: "subject", type: "string", required: true },
        { name: "body", type: "string", required: true },
      ],
    },
  ],
  steps: [
    {
      id: "s1",
      type: "user",
      content:
        "Đặt giúp tôi vé từ Hà Nội đến Sài Gòn vào thứ Sáu tuần sau (2026-11-06), rồi gửi lịch trình qua email an@example.com.",
    },
    {
      id: "s2",
      type: "thought",
      content: "Cần tìm chuyến bay trước, rồi đặt vé, cuối cùng gửi email.",
    },
    {
      id: "s3",
      type: "tool_call",
      tool: "search_flights",
      args: { origin: "HAN", destination: "SGN", date: "2026-11-06" },
    },
    {
      id: "s4",
      type: "tool_result",
      content:
        '[{"flight_id":"VN213","depart":"07:00","price":1450000},{"flight_id":"VJ131","depart":"09:30","price":990000}]',
    },
    {
      id: "s5",
      type: "tool_call",
      tool: "book_flight",
      args: { flight_id: "VN213", passenger_name: "Nguyen Van A" },
    },
    {
      id: "s6",
      type: "tool_result",
      content: '{"status":"confirmed","booking_ref":"X7K2PQ"}',
    },
    {
      id: "s7",
      type: "tool_call",
      tool: "search_flights",
      args: { origin: "HAN", destination: "SGN", date: "2026-11-06" },
    },
    {
      id: "s8",
      type: "tool_result",
      content:
        '[{"flight_id":"VN213","depart":"07:00","price":1450000},{"flight_id":"VJ131","depart":"09:30","price":990000}]',
    },
    {
      id: "s9",
      type: "tool_call",
      tool: "send_email",
      args: {
        to: "an@example.com",
        subject: "Lịch trình HAN → SGN",
        body: "Mã đặt chỗ X7K2PQ, chuyến VN213 07:00 ngày 2026-11-06.",
      },
    },
    { id: "s10", type: "tool_result", content: '{"sent":true}' },
    {
      id: "s11",
      type: "assistant",
      content:
        "Tôi đã đặt chuyến VN213 lúc 07:00 ngày 06/11 (mã X7K2PQ) và gửi lịch trình tới an@example.com.",
    },
  ],
};
