# Hướng dẫn: Xây dựng hệ thống cảnh báo chấm công real-time
## Dùng Base.vn + n8n + MCP

**Đối tượng:** Admin / IT / Người phụ trách vận hành dùng Base.vn  
**Yêu cầu:** Có tài khoản Base.vn (extapi) + n8n instance  
**Thời gian setup:** ~2-4 giờ

---

## Tổng quan hệ thống

Hệ thống tự động đọc dữ liệu lịch ca + chấm công từ Base.vn mỗi 5 phút, phát hiện bất thường và gửi cảnh báo về nhóm chat của từng bộ phận.

```
Base.vn (lịch ca + chấm công)
    ↓ đọc qua MCP mỗi 5 phút
n8n (xử lý logic, so sánh)
    ↓ phát hiện vấn đề
Base Messenger / Telegram / Slack
    (cảnh báo theo từng nhóm)
```

**Bạn nhận được gì:**
- 🟢 Nhân viên vào đúng giờ → im lặng
- 🔔 Chưa check-in sau 10 phút → cảnh báo SM
- 🔴 Vắng sau 60 phút → cảnh báo + hỏi xác nhận
- 🟡 Vào trễ → ghi nhận ngay khi quẹt thẻ
- 🚨 Chưa checkout sau 60 phút → nhắc SM xác nhận về hay OT

---

## Phần 1 — Chuẩn bị

### 1.1 Yêu cầu tối thiểu

| Thành phần | Yêu cầu | Ghi chú |
|---|---|---|
| Base.vn | Gói có `extapi` | Cần bật tính năng API |
| n8n | Self-hosted hoặc Cloud | Khuyến nghị self-hosted |
| MCP Server | Máy chủ riêng chạy MCP | Xem phần 1.3 |
| Base Messenger | Webhook URL cho từng nhóm | Setup trong Base.vn |

### 1.2 Lấy thông tin từ Base.vn

Đăng nhập Base.vn → **Cài đặt** → **Tích hợp API** → lấy:
- `Company ID`
- `API Key` (extapi)

> ⚠️ Giữ API Key bảo mật. Không chia sẻ hoặc để trong code công khai.

### 1.3 Cài đặt MCP Server cho Base.vn

MCP (Model Context Protocol) là lớp trung gian giúp n8n gọi Base.vn API một cách chuẩn hóa.

**Option A — Docker (khuyến nghị):**
```bash
docker run -d \
  -p 8081:8081 \
  -e BASE_COMPANY_ID=your_company_id \
  -e BASE_API_KEY=your_api_key \
  your-mcp-base-image
```

**Option B — Node.js trực tiếp:**
```bash
git clone https://github.com/your-org/mcp-base
cd mcp-base
npm install
BASE_COMPANY_ID=xxx BASE_API_KEY=xxx node server.js
```

Sau khi chạy, test bằng:
```bash
curl -X POST http://localhost:8081/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

Nếu trả về `{"result":{"protocolVersion":...}}` → MCP đang chạy.

---

## Phần 2 — Cấu hình

### 2.1 Xác định Store/Bộ phận cần theo dõi

Trước khi build workflow, cần mapping rõ:

| Thông tin | Lấy ở đâu | Dùng để làm gì |
|---|---|---|
| `office_id` | Base.vn → Cơ cấu tổ chức → ID của từng phòng/cửa hàng | Fallback routing khi shift không có jobsite |
| `jobsite_id` | Base.vn → Lịch làm việc → Địa điểm | Primary routing → biết alert gửi về nhóm nào |
| `timesheet_id` | Base.vn → Bảng chấm công → ID | Dùng để fetch shift theo bảng công |
| Webhook URL | Base.vn → Nhóm chat → Cài đặt → Webhook | Địa chỉ gửi cảnh báo |

**Cách lấy office_id / jobsite_id:**
1. Vào Base.vn → mở DevTools (F12) → tab Network
2. Thực hiện thao tác trên trang (mở nhóm, xem bảng công)
3. Tìm request API → đọc ID trong response

Hoặc gọi trực tiếp qua MCP:
```
tool: hrm_list_offices → trả về list offices với id
tool: hrm_list_timesheets → trả về list bảng công với id
```

### 2.2 Lấy Webhook URL

Trong Base Messenger:
1. Mở nhóm chat của bộ phận → **Quản lý nhóm**
2. **Tích hợp** → **Webhook**
3. Tạo mới → copy URL

Mỗi bộ phận/cửa hàng nên có **1 nhóm riêng** và **1 webhook riêng** để alert không bị lẫn.

---

## Phần 3 — Build Workflow trên n8n

### 3.1 Tổng quan workflow (8 node)

```
[Cron 5'] → [Init Time] → [In Hours?] → [Fetch Data] → [Compute Alerts] → [Has Alert?] → [Send] → [Log]
```

### 3.2 Node 1 — Cron 5'

- Type: **Schedule Trigger**
- Interval: Every **5 minutes**

### 3.3 Node 2 — Init Time (ICT)

- Type: **Code**
- Tính `now_unix`, `midnight_unix`, `date_str` theo múi giờ của bạn

```javascript
const now = new Date();
const offsetMs = 7 * 3600 * 1000; // UTC+7, đổi theo múi giờ của bạn
const nowLocal = new Date(now.getTime() + offsetMs);

const midnightMs = Date.UTC(
  nowLocal.getUTCFullYear(), nowLocal.getUTCMonth(), nowLocal.getUTCDate()
) - offsetMs;

const dateStr = nowLocal.getUTCFullYear() + '-'
  + String(nowLocal.getUTCMonth()+1).padStart(2,'0') + '-'
  + String(nowLocal.getUTCDate()).padStart(2,'0');

return [{ json: {
  now_unix:      Math.floor(now.getTime() / 1000),
  midnight_unix: Math.floor(midnightMs / 1000),
  end_unix:      Math.floor(midnightMs / 1000) + 86399,
  date_str:      dateStr,
  hour_local:    nowLocal.getUTCHours(),
} }];
```

### 3.4 Node 3 — In Hours? (IF node)

Chỉ chạy trong giờ hoạt động, tránh tốn tài nguyên ban đêm:

```
Condition: {{ $json.hour_local }} >= 6  AND  {{ $json.hour_local }} < 22
```

Thay `6` và `22` theo giờ mở/đóng cửa của bạn.

### 3.5 Node 4 — Fetch Data (Code node)

Đây là node quan trọng nhất — gọi MCP lấy toàn bộ dữ liệu cần thiết.

**Cấu hình MCP:**
```javascript
const MCP_URL = 'http://your-mcp-server:8081/mcp'; // URL MCP của bạn
const MCP_KEY = 'your-mcp-bearer-key';              // Bearer key
```

**Logic fetch:**
```javascript
// PHASE A: Lấy tất cả ca làm việc hôm nay (paginate)
const allShifts = [];
for (let page = 1; page <= 20; page++) {
  const r = await safe('schedule_list_shifts', {
    start_time: String(midnightUnix),
    end_time:   String(endUnix),
    page,
  });
  if (!r || !(r.shifts || r.data || Array.isArray(r)).length) break;
  const ps = r.shifts || r.data || r;
  allShifts.push(...ps);
  if (ps.length < 100) break;
}

// PHASE B: Fetch riêng từng bảng công (workaround API bug khi dùng cả timesheet_id + page)
// ⚠️ KHÔNG truyền "page" khi đã có "timesheet_id"
const MY_TIMESHEETS = ['YOUR_TS_ID_1', 'YOUR_TS_ID_2']; // điền timesheet_id của bạn
for (const tsId of MY_TIMESHEETS) {
  const r = await safe('schedule_list_shifts', {
    start_time:   String(midnightUnix),
    end_time:     String(endUnix),
    timesheet_id: tsId,
    // KHÔNG có "page" ở đây
  });
  // dedup rồi push vào allShifts
}

// Fetch song song: NV + check-in + nghỉ phép + accounts
const [empsResult, checkinRaw, timeoffRaw, accountsRaw] = await Promise.all([
  safe('hrm_list_employees', {}),
  safe('checkin_get_logs', { start_date: midnightUnix, end_date: endUnix }),
  safe('timeoff_list_timeoffs', { start_date_from: dateStr, start_date_to: dateStr, status: 'approved' }),
  safe('account_list_users', { per_page: 500 }),
]);
```

**Filter nhân viên đang hoạt động (tránh bug partime):**
```javascript
// ⚠️ Không dùng e.status — Base.vn đánh "Terminated" cho HĐ có thời hạn dù chưa hết hạn
// ⚠️ Kiểm tra terminated_date > 0 trước — partime không có ngày kết thúc → terminated_date = null
const activeEmps = allEmps.filter(e =>
  e && e.id &&
  (String(e.is_terminated) === '0' ||
   (Number(e.terminated_date) > 0 && Number(e.terminated_date) > nowTs))
);
```

### 3.6 Node 5 — Compute Alerts (Code node)

Đây là engine logic chính. Cấu trúc gồm 4 bước:

**Bước 1 — Config store của bạn:**
```javascript
// Điền jobsite_id và office_id của từng bộ phận
const WHITELIST_JOBSITE = {
  'YOUR_JOBSITE_ID_1': { code: 'STORE_A' },
  'YOUR_JOBSITE_ID_2': { code: 'STORE_B' },
};
const WHITELIST_OFFICE = {
  'YOUR_OFFICE_ID_1': { code: 'STORE_A' },
  'YOUR_OFFICE_ID_2': { code: 'STORE_B' },
};

// Webhook URL của từng nhóm
const STORE_WEBHOOK = {
  'STORE_A': 'https://bot.base.vn/v1/webhook/send/YOUR_WEBHOOK_A',
  'STORE_B': 'https://bot.base.vn/v1/webhook/send/YOUR_WEBHOOK_B',
};
```

**Bước 2 — Thresholds (điều chỉnh theo nhu cầu):**
```javascript
const ON_TIME_BUFFER    = 5  * 60; // 5' grace — trễ ≤5' vẫn tính đúng giờ
const LATE_WARN_START   = 10 * 60; // Cảnh báo sau 10' chưa vào
const ABSENT_START      = 60 * 60; // Vắng sau 60' chưa vào
const OUT_MISSING_START = 60 * 60; // Chưa checkout sau 60' ca kết thúc
const CRON_INTERVAL     = 5  * 60; // Khớp với cron — dùng để tránh spam
```

**Bước 3 — Logic phân loại alert:**

| State | Điều kiện |
|---|---|
| `on_time` | Có check-in AND trễ ≤ 5' AND mới quẹt trong 5' gần nhất |
| `late` | Có check-in AND trễ > 5' AND mới quẹt trong 5' gần nhất |
| `late_warn` | Không có check-in AND đã qua 10' sau giờ vào |
| `absent` | Không có check-in AND đã qua 60' sau giờ vào |
| `out_missing` | Có check-in, không có check-out AND đã qua 60' sau giờ ra |

**Bước 4 — Dedup (chống spam):**
```javascript
// Lưu alert đã gửi trong ngày — tự reset khi sang ngày mới
const gState = $getWorkflowStaticData('global');
if (gState._date !== dateStr) { gState._date = dateStr; gState._sent = {}; }
const sentToday = gState._sent;

// Trước khi gửi, kiểm tra:
const key = `${dateStr}_${empId}_${shiftId}_${alertType}`;
if (sentToday[key]) continue; // đã gửi rồi → skip
sentToday[key] = nowTs;        // đánh dấu đã gửi
```

### 3.7 Node 6 — Has Alert? (IF node)

```
Condition: {{ $json.message }} is not empty
```

### 3.8 Node 7 — Send (HTTP Request)

```
Method: POST
URL: {{ $json.webhook_url }}
Headers:
  Content-Type: application/x-www-form-urlencoded
Body (raw string):
  bot_username=base_message&bot_name=YOUR_BOT_NAME&base_content={{ encodeURIComponent($json.message) }}
```

> **Lưu ý quan trọng:** Base Messenger webhook KHÔNG nhận JSON body — phải dùng `application/x-www-form-urlencoded`.

### 3.9 Node 8 — Log

```javascript
const results = $input.all().map(item => ({
  store:  item.json.store,
  emp:    item.json.emp_name,
  type:   item.json.alert_type,
  status: item.json.statusCode,
}));
console.log('Alerts sent:', JSON.stringify(results));
return $input.all();
```

---

## Phần 4 — Format tin nhắn

Tự customize theo văn hóa công ty, ví dụ:

```javascript
function buildMessage(type, empName, mention, inTime, nowTime, minsLate, storeCode, shiftStart, shiftEnd) {
  const pin = `\n📍 ${storeCode} · Ca ${shiftStart}-${shiftEnd}`;
  const at  = mention ? `@${mention}` : empName;

  if (type === 'on_time')     return `✅ ${empName} · ${inTime} · Đúng giờ${pin}`;
  if (type === 'late')        return `⚠️ ${at} · ${inTime} · Trễ ${minsLate}'${pin}`;
  if (type === 'late_warn')   return `🔔 ${at} · ${nowTime} · Chưa check-in${pin}`;
  if (type === 'absent')      return `🔴 ${at} · ${nowTime} · Vắng >60'\n👉 Xác nhận: nghỉ phép hay vắng?${pin}`;
  if (type === 'out_missing') return `🕐 ${at} · ${nowTime} · Chưa checkout >60'\n👉 Về hay OT?${pin}`;
  return '';
}
```

**Gợi ý:** Tắt `on_time` nếu không muốn spam khi mọi người vào đúng giờ — chỉ alert khi có vấn đề.

---

## Phần 5 — Quirks của Base.vn API (phải biết)

Những điều không có trong tài liệu chính thức nhưng ảnh hưởng trực tiếp:

| # | Vấn đề | Xử lý |
|---|---|---|
| 1 | `schedule_list_shifts` với `timesheet_id` + `page` → trả `[]` | PHASE B: bỏ tham số `page` |
| 2 | `s_time`, `e_time` là **string** unix, không phải number | `parseInt()` trước khi tính toán |
| 3 | `sw.time` (swipe time) là **string** → cộng string thay vì cộng số | `Number(sw.time)` |
| 4 | `checkout` flag trong checkin_get_logs luôn = 0 | Ignore flag — dùng time-based: swipe đầu = IN, swipe cuối = OUT |
| 5 | `is_terminated` là **string** `'0'`/`'1'`, không phải boolean | `String(e.is_terminated) === '0'` |
| 6 | `terminated_date = null` cho partime → `Number(null) = 0` | Guard: `Number(e.terminated_date) > 0` trước khi so sánh |
| 7 | Webhook reject Content-Type: application/json | Dùng `application/x-www-form-urlencoded` |
| 8 | MCP cần 3 HTTP call (không phải 1) | initialize → notifications/initialized → tools/call |

---

## Phần 6 — Vận hành

### 6.1 Kiểm tra workflow đang chạy

Trên n8n → **Executions** → lọc theo workflow → xem:
- Status: ✅ Success hay ❌ Error
- Duration: thường 4-15s/run là bình thường
- Nếu >60s → có thể MCP timeout → kiểm tra kết nối

### 6.2 Debug khi alert sai

Thêm log vào Compute Alerts node để debug:
```javascript
// Thêm vào _stats
_stats: {
  shifts_total,       // tổng ca lấy được
  active_emps,        // NV đang active được match với ca
  skipped_terminated, // NV bị skip (đã nghỉ)
  checkin_records,    // số bản ghi chấm công
  alerts_fired,       // số alert gửi lần này
  fetch_errors,       // lỗi MCP call nếu có
}
```

Nếu `active_emps = 0` → filter NV đang bị sai.  
Nếu `shifts_total = 0` → PHASE A/B không lấy được ca → kiểm tra timesheet_id.  
Nếu `checkin_records = 0` → API checkin trả rỗng → kiểm tra tham số ngày.

### 6.3 Mở rộng thêm store

1. Lấy `jobsite_id` + `office_id` + `timesheet_id` của store mới
2. Thêm vào `WHITELIST_JOBSITE`, `WHITELIST_OFFICE`, `STORE_WEBHOOK`
3. Thêm `timesheet_id` vào `PHASE_B_TIMESHEETS` nếu PHASE A bỏ sót
4. Tạo nhóm Base Messenger + lấy webhook URL mới

### 6.4 Điều chỉnh thresholds

Tùy văn hóa công ty:
- Muốn cảnh báo sớm hơn: giảm `LATE_WARN_START` (5' thay vì 10')
- Muốn ít cảnh báo: tăng `ON_TIME_BUFFER` (10' thay vì 5')
- Ca ngắn (<4h): giảm `OUT_MISSING_START` (30' thay vì 60')

---

## Phần 7 — Kiến trúc nâng cao (tùy chọn)

### 7.1 Escalation

Khi NV vắng mà SM không phản hồi sau 30' → tự động gửi lên cấp trên:

```
absent → 30' không có action → alert Manager
Manager → 30' không phản hồi → alert Director
```

Implement: thêm key `absent_unresolved_{empId}` vào static data, check ở mỗi cycle.

### 7.2 EOD Summary (23:30)

Tạo workflow riêng chạy 1 lần lúc cuối ngày, tổng kết:
- Tổng ca / ca đủ chấm công / ca thiếu
- Danh sách vắng không giải trình
- % chuyên cần của ngày

### 7.3 Correction Reminder (21:30)

Nhắc SM check và bổ sung check-in/out còn thiếu trước khi hệ thống chốt ngày.

---

## Checklist setup

- [ ] Base.vn extapi key đã có
- [ ] MCP server đang chạy và reachable từ n8n
- [ ] Đã mapping đủ: office_id / jobsite_id / timesheet_id cho từng bộ phận
- [ ] Webhook URL đã tạo cho từng nhóm Base Messenger
- [ ] WHITELIST_JOBSITE / WHITELIST_OFFICE / STORE_WEBHOOK đã điền đúng
- [ ] PHASE_B_TIMESHEETS đã có đủ timesheet_id
- [ ] Test trên môi trường sandbox trước khi push production
- [ ] Cron interval = 5' và operating hours đã set đúng múi giờ
- [ ] Dedup logic đã bật (tránh spam khi restart n8n)

---

*Tài liệu này hướng dẫn cách xây dựng hệ thống. Logic cụ thể (threshold, format tin nhắn, số bộ phận) tùy chỉnh theo nhu cầu từng tổ chức.*