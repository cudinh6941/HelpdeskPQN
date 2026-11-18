# SKILLUI.md — Hệ thiết kế Helpdesk (phong cách Plain / Linear)

> Tài liệu này là **nguồn sự thật duy nhất** về giao diện cho dự án Next.js + Tailwind CSS + shadcn/ui.
> AI/dev phải đọc toàn bộ file này **trước khi** tạo hoặc sửa bất kỳ component UI nào.
> Khi có xung đột giữa file này và thói quen mặc định của shadcn/Tailwind, **file này thắng**.

---

## 0. Nguồn gốc & độ tin cậy của các giá trị

Các giá trị dưới đây được trích từ 2 ảnh chụp màn hình tham chiếu:

- **Ảnh 1 (Queue):** bảng hàng đợi ticket, nhóm "High 3", cột SLA / Customer / Topic.
- **Ảnh 2 (Thread):** popover thảo luận "Discussion in #engineering" đặt trên nền mờ, phía sau lộ ra panel thuộc tính bên phải (Tier, Product Area, Discussions, Annie Atkins, Email, ID).

Ghi chú về độ chính xác:

| Loại | Trạng thái |
|---|---|
| Màu hex, kích thước px | **Ước lượng** từ ảnh (sai số ±1–2px / ±2% sắc độ). Dùng làm token, đừng hard-code rải rác. |
| Bố cục 3 cột | **Suy ra** từ ảnh 2 (nội dung chính + panel thuộc tính bên phải) và ảnh 1 (danh sách). Cột trái là danh sách hàng đợi. |
| Tab Reply công khai / Internal note | **Không xuất hiện trong ảnh.** Phần §9 là thiết kế mở rộng, nhất quán với hệ thống. |
| Font | Trông giống **Inter** (hoặc một neo-grotesque tương đương). Dùng Inter. |

Nguyên tắc chủ đạo: **công cụ làm việc cho người trực ticket cả ngày** — mật độ cao, tĩnh, dễ quét mắt. Không có "điểm nhấn trang trí". Màu chỉ xuất hiện khi mang thông tin (khẩn cấp, gói khách hàng, loại topic, người dùng).

---

## 1. Triết lý (7 điều)

1. **Viền 1px thay cho đổ bóng.** Bề mặt trong luồng (card, row, input, badge) phân tách bằng viền 1px. Bóng chỉ dành cho lớp *nổi* (popover, dialog, dropdown) và phải cực nhẹ.
2. **Trung tính là nền, màu là tín hiệu.** 95% pixel là trắng / xám ấm / mực đen. Màu bão hòa chỉ nằm trong icon nhỏ, chấm tier, và badge SLA khẩn cấp.
3. **Mật độ cao nhưng thoáng nhờ nhịp.** Hàng 72px chứa 2 dòng thông tin; khoảng trắng nằm ở padding, không ở dòng trống.
4. **Một bán kính cho mỗi vai trò.** Checkbox 4px, badge/nút 6px, logo 6px, card 10px, popover 12px. Không dùng `rounded-2xl` hay `rounded-full` cho thứ không phải avatar/pill trạng thái.
5. **Phân cấp bằng sắc độ chữ, không bằng cỡ chữ.** Cả giao diện chỉ dùng 2 cỡ chính (15px và 13px); khác biệt thể hiện bằng màu `ink` / `ink-muted` / `ink-faint` và độ đậm 400/500.
6. **Icon là ngôn ngữ.** Icon 14–16px, nét 1.5px, đặt trong badge, đầu dòng và hành động. Không dùng emoji làm icon UI.
7. **Chuyển động chỉ đáp lại hành động** (mở popover, đổi tab, chọn hàng). Không có hiệu ứng vào trang, không có hover nảy.

---

## 2. Design tokens

### 2.1 Màu (CSS variables, chuẩn shadcn)

Đặt trong `app/globals.css`. Tên biến giữ nguyên chuẩn shadcn để các component có sẵn nhận đúng màu; các token riêng của helpdesk đặt thêm bên dưới.

```css
@layer base {
  :root {
    /* ===== Bề mặt ===== */
    --background: #F4F3F1;          /* nền app, xám ấm rất nhạt */
    --foreground: #17181C;          /* mực chính (không phải #000) */

    --card: #FFFFFF;                /* bề mặt nổi trên nền */
    --card-foreground: #17181C;
    --popover: #FFFFFF;
    --popover-foreground: #17181C;

    --muted: #F0EFEC;               /* hover hàng, nền vùng phụ */
    --muted-foreground: #6B6F77;    /* chữ phụ (header cột, tên khách sau dấu "/") */

    --border: #E7E6E2;              /* viền 1px tiêu chuẩn */
    --border-subtle: #EFEEEA;       /* đường kẻ phân cách hàng trong bảng */
    --input: #E2E1DD;               /* viền input / checkbox */
    --ring: #3B6FE0;                /* focus ring */

    --primary: #17181C;             /* nút chính = mực đen, KHÔNG phải xanh */
    --primary-foreground: #FFFFFF;
    --secondary: #F0EFEC;
    --secondary-foreground: #17181C;
    --accent: #F0EFEC;
    --accent-foreground: #17181C;
    --destructive: #D6453D;
    --destructive-foreground: #FFFFFF;

    --radius: 0.5rem;               /* 8px làm gốc; xem 2.4 */

    /* ===== Chữ (bổ sung) ===== */
    --ink-faint: #9A9EA5;           /* timestamp, placeholder, icon thụ động */

    /* ===== SLA ===== */
    --sla-urgent-bg: #F8B99D;       /* đào/cam nhạt: sắp vi phạm SLA */
    --sla-urgent-fg: #3A1D0E;
    --sla-neutral-bg: #E7E7EA;      /* xám lạnh nhạt: còn thời gian */
    --sla-neutral-fg: #3B3E45;
    --sla-breached-bg: #F5C4C0;     /* đã vi phạm */
    --sla-breached-fg: #5C1712;

    /* ===== Tier khách hàng (chỉ dùng cho chấm/diamond 8–10px) ===== */
    --tier-enterprise: #3B7BEA;
    --tier-pro: #2FC98E;
    --tier-free: #9A9EA5;

    /* ===== Tín hiệu khác ===== */
    --priority-high: #EE9B3B;       /* icon "≡" mức High */
    --action-reply: #3B6FE0;        /* icon mũi tên trả lời */

    /* ===== Internal note (xem §9) ===== */
    --note-bg: #FFF8E5;
    --note-border: #F0E1AE;
    --note-ink: #6B5410;

    /* ===== Lớp phủ ===== */
    --scrim: rgba(244, 243, 241, 0.72);  /* nền mờ SÁNG phía sau popover */
  }

  /* Dark mode: tạm không hỗ trợ. Nếu thêm, phải đảo toàn bộ bằng token,
     KHÔNG dùng `dark:` rải rác trong component. */
}
```

Ánh xạ Tailwind (v3: `tailwind.config.ts` → `theme.extend.colors`; v4: `@theme inline`):

```ts
// tailwind.config.ts (v3)
extend: {
  colors: {
    border: "var(--border)",
    "border-subtle": "var(--border-subtle)",
    input: "var(--input)",
    ring: "var(--ring)",
    background: "var(--background)",
    foreground: "var(--foreground)",
    card: { DEFAULT: "var(--card)", foreground: "var(--card-foreground)" },
    muted: { DEFAULT: "var(--muted)", foreground: "var(--muted-foreground)" },
    faint: "var(--ink-faint)",
    sla: {
      urgent: "var(--sla-urgent-bg)",
      "urgent-fg": "var(--sla-urgent-fg)",
      neutral: "var(--sla-neutral-bg)",
      "neutral-fg": "var(--sla-neutral-fg)",
      breached: "var(--sla-breached-bg)",
      "breached-fg": "var(--sla-breached-fg)",
    },
    tier: { enterprise: "var(--tier-enterprise)", pro: "var(--tier-pro)", free: "var(--tier-free)" },
    note: { DEFAULT: "var(--note-bg)", border: "var(--note-border)", ink: "var(--note-ink)" },
  },
  borderRadius: { xs: "4px", sm: "6px", md: "8px", lg: "10px", xl: "12px" },
}
```

**Quy tắc màu bắt buộc**
- Nền app luôn `bg-background` (xám ấm); card/panel luôn `bg-card` (trắng). Trắng trên xám ấm **là** cách tạo chiều sâu, kết hợp với viền 1px.
- Không dùng `bg-white`, `text-black`, `text-gray-*`, `border-gray-*` trực tiếp. Chỉ dùng token.
- Không có màu thương hiệu bão hòa làm nền khối lớn. Nút chính là mực đen.
- Màu `tier-*` và `priority-high` chỉ xuất hiện ở icon/chấm, **không** tô nền badge.

### 2.2 Chữ

Font: **Inter** (qua `next/font/google`), bật `font-feature-settings: "cv11", "ss01"` nếu muốn "a" một tầng giống ảnh; mặc định không bật cũng chấp nhận được.

```ts
// app/layout.tsx
import { Inter } from "next/font/google";
const sans = Inter({ subsets: ["latin", "vietnamese"], variable: "--font-sans", display: "swap" });
```

```css
body {
  font-family: var(--font-sans), ui-sans-serif, system-ui, sans-serif;
  font-size: 15px;
  line-height: 1.4;
  letter-spacing: -0.005em;
  color: var(--foreground);
  background: var(--background);
  -webkit-font-smoothing: antialiased;
}
```

| Token | Cỡ / line-height | Độ đậm | Màu | Dùng cho |
|---|---|---|---|---|
| `text-body` | 15px / 22px | 400 | `foreground` | Nội dung tin nhắn, tên công ty, tiêu đề topic (500 cho tiêu đề topic) |
| `text-body-strong` | 15px / 22px | 500 | `foreground` | Tên người gửi, tiêu đề topic, tiêu đề popover, nhãn nhóm ("High") |
| `text-meta` | 13px / 18px | 400 | `muted-foreground` | Header cột (SLA, Customer, Topic), nhãn thuộc tính ở panel phải |
| `text-meta-faint` | 13px / 18px | 400 | `ink-faint` | Timestamp ("2m ago", "Just now"), "Started 2m ago", placeholder |
| `text-badge` | 13px / 16px | 500 (SLA) / 400 (tier, topic) | theo badge | Nội dung badge |

Quy tắc:
- **Chỉ 2 cỡ**: 15px và 13px. Không thêm 14px, 16px, 18px, 24px vào vùng làm việc. Tiêu đề trang (nếu có) tối đa 17px / 500.
- **Số có `tabular-nums`** (SLA, ID, đếm "3") để không nhảy khi đổi giá trị.
- **Không dùng chữ IN HOA**, không `tracking-wider` cho nhãn. Header cột viết thường, sentence case ("SLA" là viết tắt nên giữ nguyên).
- Dấu `/` giữa công ty và người liên hệ: công ty `foreground`, dấu `/` và tên người `muted-foreground`.
- Không italic. Không gạch chân (trừ link trong nội dung tin nhắn).

### 2.3 Khoảng cách & mật độ

Lưới nền **4px**. Chỉ dùng các bước: 4, 6, 8, 12, 16, 20, 24, 32.

| Vị trí | Giá trị |
|---|---|
| Chiều cao hàng trong bảng queue | **72–74px** (`py-3` + 2 dòng: 24px nội dung + 6px + 24px badge) |
| Padding ngang card/bảng | 16px (`px-4`) |
| Header nhóm ("≡ High 3") | cao 44px, `px-4`, icon 16px cách chữ 8px |
| Header cột | cao 32px, `text-meta` |
| Khoảng cách giữa các cột trong hàng | 16px (`gap-x-4`) |
| Khoảng cách dòng chính → hàng badge | 6px |
| Khoảng cách giữa các badge cùng hàng | 8px |
| Padding popover (header) | 16px ngang, 12px dọc |
| Padding vùng tin nhắn | 16px |
| Khoảng cách giữa 2 tin nhắn | 16–20px |
| Avatar → khối chữ | 8px |
| Tên người gửi → timestamp | 8px |
| Padding composer | 16px, thanh công cụ cách đáy 12px |
| Hàng thuộc tính (panel phải) | cao 32px, `gap-x-3` |

Không dùng `space-y-8`, `py-16`, `p-10` trong vùng làm việc. Nếu thấy cần padding > 24px, bạn đang làm landing page, không phải helpdesk.

### 2.4 Bán kính, viền, bóng

| Phần tử | Radius | Viền | Bóng |
|---|---|---|---|
| Checkbox | 4px | 1px `input` | không |
| Badge (SLA, tier, topic) | 6px | SLA: không viền; tier/topic: 1px `border` | không |
| Nút | 6px | 1px `border` (secondary) hoặc không (primary) | không |
| Input / composer | 8px | 1px `border` | không |
| Logo công ty | 6px | không | không |
| Avatar người | 9999px | không | không |
| Card / bảng chính | 10px | **1px `border`** | không (hoặc `0 1px 2px rgba(23,24,28,.04)` nếu cần tách khỏi nền) |
| Popover / dialog | 12px | 1px `border` | `0 8px 24px -4px rgba(23,24,28,.10), 0 0 0 1px rgba(23,24,28,.04)` |

Quy tắc viền/bóng:
- **Phân tách = viền 1px** (`border border-border`, `border-b border-border-subtle`). Đây là quy tắc mặc định cho mọi thứ nằm trong luồng trang.
- **Bóng** chỉ dành cho lớp nổi (popover, dialog, dropdown, tooltip), một lớp duy nhất, độ mờ ≤ 10%, blur lớn, offset Y nhỏ. Không bao giờ chồng 2 bóng cùng kiểu, không `shadow-md/lg/xl/2xl` của Tailwind.
- Đường kẻ giữa các hàng dùng `border-subtle` (nhạt hơn `border`).
- Không dùng `ring` làm viền trang trí; `ring` chỉ cho focus.

---

## 3. Bố cục 3 cột

```
┌───────────────────────────────────────────────────────────────────────────┐
│  [Queue list 340px]  │  [Conversation  flex-1, max 760px]  │ [Properties 300px] │
│  ≡ High 3            │  Header: tiêu đề + trạng thái       │ Tier        Enterprise │
│  ─ row ─             │  ────────────────────────────────── │ Product Area   —       │
│  ─ row ─             │  Tin nhắn / ghi chú nội bộ          │ Discussions            │
│  ─ row ─             │                                     │   # engineering        │
│  ≡ Medium 7          │  ┌────────────────────────────────┐ │ ───────────────        │
│  ...                 │  │ Composer: [Reply | Internal]   │ │ (avatar) Annie Atkins  │
│                      │  └────────────────────────────────┘ │ Email   ID             │
└───────────────────────────────────────────────────────────────────────────┘
```

| Cột | Rộng | Nền | Ghi chú |
|---|---|---|---|
| Danh sách (trái) | 340px cố định (`w-[340px]`), co về 0 trên mobile | `bg-background` (chính hàng là `bg-card`) | Cuộn độc lập |
| Hội thoại (giữa) | `flex-1 min-w-0`, nội dung `max-w-[760px]` | `bg-card` | Composer ghim đáy |
| Thuộc tính (phải) | 300px cố định, ẩn dưới `xl` (mở bằng sheet) | `bg-background` | Mỗi cột cuộn riêng |

- Giữa các cột là **một đường kẻ dọc 1px `border`**, không khoảng hở, không card nổi riêng cho từng cột.
- Toàn bộ shell: `h-dvh grid grid-cols-[340px_minmax(0,1fr)_300px]`, mỗi cột `overflow-y-auto`.
- **Chế độ bảng rộng** (như ảnh 1, khi không mở hội thoại): bảng chiếm toàn bộ bề ngang, lưới cột hàng:
  `grid-cols-[16px_16px_88px_minmax(220px,1fr)_minmax(260px,1.4fr)]` = checkbox | icon trả lời | SLA | Customer | Topic, `gap-x-4`.
- Panel thuộc tính: mỗi hàng là `label (text-meta) | value (text-body)`, nhãn rộng 96px, không viền giữa các hàng; chỉ có 1 đường kẻ ngang trước khối thông tin khách hàng.

---

## 4. Bảng hàng đợi (Queue table)

### 4.1 Nhóm theo độ ưu tiên

Header nhóm: `[icon priority 16px, màu priority-high]  High  3`
- Tên nhóm: `text-body-strong`. Số đếm: `text-body` màu `muted-foreground`, cách tên 8px.
- Icon priority là biểu tượng 3 gạch ngang giảm dần độ dài (≡). High = `priority-high`; Medium = `faint`; Low = `faint`; Urgent = `destructive`.
- Nhóm có thể thu gọn; chevron chỉ hiện khi hover header.

### 4.2 Hàng ticket

Thứ tự trái → phải:

1. **Checkbox** 16×16, radius 4px, viền 1px `input`, nền `card`. Khi checked: nền `foreground`, dấu tích trắng. Hiện luôn (không chỉ khi hover).
2. **Icon hành động** (mũi tên trả lời ↩) 16px, màu `action-reply`. Biểu thị "đang chờ mình trả lời". Hàng chờ bên khách: dùng icon khác, màu `faint`.
3. **Badge SLA** (xem §5.1).
4. **Ô Customer:**
   - Dòng 1: logo công ty 24×24 radius 6px + `Tên công ty` (`foreground`) + ` / ` + `Tên người` (`muted-foreground`), `text-body`, cách logo 8px.
   - Dòng 2: **Tier badge** (§5.2), thụt lề bằng chiều rộng logo + gap (32px) để thẳng hàng với chữ.
5. **Ô Topic:**
   - Dòng 1: tiêu đề ticket, `text-body-strong`, `truncate`.
   - Dòng 2: hàng **Topic badge** (§5.3), `gap-2`, `overflow-hidden` (badge cuối bị cắt mượt khi hết chỗ, như "Onboar…" trong ảnh).

Trạng thái hàng:
- Mặc định: `bg-card`, kẻ dưới `border-b border-border-subtle` (hàng cuối không kẻ).
- Hover: `bg-muted/60` (không đổi bóng, không nâng).
- Đã chọn (đang mở): `bg-muted` + thanh 2px `foreground` ở mép trái. Không dùng nền xanh.
- Chưa đọc: tên công ty `text-body-strong`; đã đọc: `text-body`.
- Focus bàn phím: `ring-2 ring-ring ring-offset-0` bên trong hàng (inset).

```tsx
// components/queue/queue-row.tsx
export function QueueRow({ ticket, selected }: Props) {
  return (
    <div
      role="row"
      data-selected={selected}
      className="grid grid-cols-[16px_16px_88px_minmax(220px,1fr)_minmax(260px,1.4fr)] items-start gap-x-4
                 border-b border-border-subtle px-4 py-3 last:border-b-0
                 hover:bg-muted/60 data-[selected=true]:bg-muted"
    >
      <Checkbox className="mt-[3px]" />
      <ReplyIcon className="mt-[3px] size-4 text-[var(--action-reply)]" />
      <SlaBadge remainingMs={ticket.slaMs} state={ticket.slaState} />
      <CustomerCell company={ticket.company} contact={ticket.contact} tier={ticket.tier} />
      <TopicCell title={ticket.title} topics={ticket.topics} />
    </div>
  );
}
```

---

## 5. Badge

Mọi badge: `inline-flex items-center h-6 rounded-sm text-[13px] leading-4`. Chiều cao cố định 24px.

### 5.1 Badge SLA (có nền, không viền)

| Trạng thái | Nền | Chữ | Khi nào |
|---|---|---|---|
| `urgent` | `sla-urgent-bg` (đào) | `sla-urgent-fg` | Còn dưới ngưỡng cảnh báo (mặc định < 30 phút) |
| `neutral` | `sla-neutral-bg` (xám lạnh) | `sla-neutral-fg` | Còn nhiều thời gian |
| `breached` | `sla-breached-bg` | `sla-breached-fg` | Đã quá hạn, hiển thị `-12m` hoặc "Overdue" |

- `px-2` (8px), `font-medium`, `tabular-nums`, `rounded-sm` (6px), không icon, không viền.
- Định dạng thời gian: `13m 22s`, `1h 01m`, `1h 45m` (giờ + phút 2 chữ số). Dưới 1 giờ hiện `Xm Ys` và **cập nhật mỗi giây**; từ 1 giờ trở lên hiện `Xh YYm`, cập nhật mỗi phút.
- Chỉ **một** màu "nóng" duy nhất trên toàn bảng: đào. Không dùng đỏ tươi, không nhấp nháy, không pulse animation.

```tsx
const slaVariants = cva(
  "inline-flex h-6 items-center rounded-sm px-2 text-[13px] font-medium leading-4 tabular-nums",
  {
    variants: {
      state: {
        urgent: "bg-sla-urgent text-sla-urgent-fg",
        neutral: "bg-sla-neutral text-sla-neutral-fg",
        breached: "bg-sla-breached text-sla-breached-fg",
      },
    },
    defaultVariants: { state: "neutral" },
  }
);
```

### 5.2 Badge Tier (viền 1px, chấm màu)

- Nền `card` (trắng), viền 1px `border`, `rounded-sm`, `px-2`, `gap-1.5`, `text-[13px]` weight 400, chữ `foreground`.
- Trước chữ là **diamond/chấm 8px** (◆) tô màu `tier-*`: Enterprise = xanh dương, Pro = xanh lục, Free = xám. Màu **chỉ** ở diamond; chữ và viền luôn trung tính.

```tsx
export function TierBadge({ tier }: { tier: "enterprise" | "pro" | "free" }) {
  return (
    <span className="inline-flex h-6 items-center gap-1.5 rounded-sm border border-border bg-card px-2 text-[13px] leading-4">
      <span aria-hidden className={cn("size-2 rotate-45 rounded-[2px]", {
        "bg-tier-enterprise": tier === "enterprise",
        "bg-tier-pro": tier === "pro",
        "bg-tier-free": tier === "free",
      })} />
      <span className="capitalize">{tier}</span>
    </span>
  );
}
```

### 5.3 Badge Topic (viền 1px, icon xám)

- Cùng khuôn với Tier badge, nhưng icon đầu là **icon Lucide 14px, nét 1.5, màu `muted-foreground`**, không tô màu.
- Ví dụ icon: Bug report → `Bug`; Technical question → `Cpu`; Onboarding → `Rocket`/`Flag`; Upgrade request → `ArrowUpFromLine`.
- Chữ `foreground`, weight 400.

### 5.4 Quy tắc chung cho badge
- Không có hơn **3 màu** khác nhau xuất hiện trong cùng một hàng.
- Không dùng `shadcn Badge variant="default"` (nền đen) hay `secondary` mặc định; ghi đè qua `cva` như trên.
- Badge không bao giờ có hover/click, trừ khi là bộ lọc, khi đó hover = `bg-muted`.
- Không bao giờ xuống dòng trong badge (`whitespace-nowrap`).

---

## 6. Panel thuộc tính (cột phải)

Từ ảnh 2: các hàng `Tier`, `Product Area`, `Discussions` (kèm các mục con `# engineering`, `# customer…` có icon Slack), rồi khối khách hàng (avatar + `Annie Atkins`, `Email`, `ID`).

- Nhãn: `text-meta` (13px, `muted-foreground`), rộng 96px, canh trên cùng.
- Giá trị: `text-body` (15px) hoặc badge (Tier dùng `TierBadge`). Giá trị rỗng hiện `—` màu `faint`, không để trống.
- Tiêu đề nhóm con ("Discussions"): `text-meta`, kèm icon 14px `faint` ở đầu.
- Mục thảo luận: `Discussion in #engineering` với icon Slack 14px, `text-body`, hover `bg-muted`, radius 6px, cao 32px, bấm mở popover §8.
- Khối khách hàng: ngăn bằng `border-t border-border`, `pt-4`, avatar 24px (có icon nguồn nhỏ 12px ở góc dưới phải, ví dụ Instagram), tên `text-body-strong`.
- ID dùng `tabular-nums`, `truncate`, có nút copy hiện khi hover.
- Mọi hàng có thể chỉnh: hover hiện viền 1px `border` và nền `card`; click mở combobox (shadcn `Popover` + `Command`).

---

## 7. Thành phần shadcn cần ghi đè

Chạy `npx shadcn@latest add` như bình thường, **rồi sửa** các file trong `components/ui/` theo bảng sau. Không giữ nguyên mặc định.

| Component | Ghi đè bắt buộc |
|---|---|
| `Button` | `rounded-sm` (6px), `h-8` mặc định (32px), `text-[13px]` hoặc `text-[15px]`, bỏ `shadow-*`. `default` = nền `primary` (mực đen). `outline`/`secondary` = nền `card`, viền 1px `border`, hover `bg-muted`. Bỏ `active:scale-*`. |
| `Badge` | Thay variants bằng `sla`, `tier`, `topic` (§5). Xóa variant mặc định đổ màu. |
| `Checkbox` | 16px, `rounded-xs` (4px), viền `input`, checked nền `foreground`. |
| `Input` / `Textarea` | `rounded-md`, viền 1px `border`, **không bóng**, focus: `border-foreground/30` + `ring-2 ring-ring/20`. Nền `card`. |
| `Tabs` | Dạng gạch chân hoặc segmented 1px (xem §9). Không dùng nền xám tròn kiểu mặc định. |
| `Popover` / `Dialog` | `rounded-xl` (12px), viền 1px, dùng đúng bóng ở §2.4. Overlay = `--scrim` (**sáng**, không đen). |
| `Avatar` | 24px mặc định, `rounded-full`, không viền. |
| `Tooltip` | Nền `foreground`, chữ trắng, 13px, `rounded-sm`, không bóng, trễ 400ms. |
| `Separator` | Luôn `bg-border` hoặc `bg-border-subtle`, 1px. |
| `Card` | Bỏ `shadow`. Dùng `rounded-lg border border-border bg-card`. Không có `CardHeader` padding 24px; dùng 16px. |

Overlay của Dialog/Popover:

```tsx
// components/ui/dialog.tsx → DialogOverlay
className="fixed inset-0 z-50 bg-[var(--scrim)] backdrop-blur-[2px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 duration-150"
```

---

## 8. Popover thảo luận (Discussion in #channel)

Cấu trúc từ ảnh 2, rộng ~400px (`w-[400px]`), `rounded-xl border border-border bg-card` + bóng nổi §2.4.

```
┌──────────────────────────────────────────────┐
│ Discussion in [slack] #engineering   ⋯   ✕   │  ← header 56px, border-b
│ Started 2m ago                                │
├──────────────────────────────────────────────┤
│ (av) Ben Braithwaite  2m ago                 │
│      Can someone take a look this issue …    │
│                                              │  ← gap 20px
│ (av) Carla Cavani  Just now                  │
│      Hmm, yep. That's a bug. I'm deploying…  │
│                                              │
├──────────────────────────────────────────────┤  ← border-t
│ Add a message                                │
│ 📎  ☺  ⚙                          [ ➤ Send ] │
└──────────────────────────────────────────────┘
```

- **Header:** dòng 1 `text-body-strong` (icon Slack 14px nằm ngay trước `#engineering`); dòng 2 `text-meta-faint`. Bên phải: nút icon `ghost` 28×28 (`MoreHorizontal`, `X`), icon 16px `muted-foreground`. Kẻ dưới 1px `border-subtle`.
- **Tin nhắn:** avatar 24px, tên `text-body-strong`, timestamp `text-meta-faint` cách tên 8px, nội dung `text-body` bắt đầu thẳng cột với tên (thụt 32px). **Không có bong bóng**, không nền, không viền quanh tin nhắn.
- **Composer:** ghim đáy, kẻ trên 1px. Placeholder `text-body` màu `faint`. Thanh công cụ: icon 16px `faint` (đính kèm, emoji, định dạng), `gap-3`, hover `foreground`.
- **Nút Send:** `h-8 rounded-sm px-3`, icon + chữ. Disabled (rỗng): nền `muted`, chữ `faint`, **không** `opacity-50`. Khi có nội dung: nền `primary`, chữ trắng.
- Phím tắt: `Enter` gửi, `Shift+Enter` xuống dòng, `Esc` đóng.

---

## 9. Tab Reply công khai vs Internal note (thiết kế mở rộng)

> Không có trong ảnh tham chiếu, được suy ra để nhất quán. Mục đích: người trực **không bao giờ gửi nhầm** ghi chú nội bộ cho khách.

### 9.1 Vị trí & hình dạng
Hai tab nằm **ngay trên ô soạn thảo**, bên trong khối composer, dạng gạch chân 1px (không phải segmented nền xám):

```
 Reply  │  Internal note            ← text-[13px], tab đang chọn: foreground + gạch chân 2px foreground
────────────────────────────────
 Write a reply to Annie…
 📎  ☺  ⚙                [ Send reply ]
```

- Tab: `h-8 px-0 mr-4 text-[13px] font-medium`; không chọn: `muted-foreground`; chọn: `foreground` + `border-b-2 border-foreground`.
- Phím tắt: `⌘ + ⇧ + R` = Reply, `⌘ + ⇧ + N` = Internal note (hiện trong tooltip).

### 9.2 Hai chế độ khác nhau rõ ràng

| | **Reply** (công khai) | **Internal note** |
|---|---|---|
| Nền composer | `card` (trắng) | `note` (#FFF8E5) |
| Viền composer | 1px `border` | 1px `note-border` |
| Icon đầu | không | `Lock` 14px màu `note-ink` |
| Placeholder | "Write a reply to {contact}…" | "Add an internal note. Only your team can see this." |
| Nút gửi | **Send reply**, nền mực đen | **Add note**, nền `note-ink`, chữ trắng |
| Thông tin người nhận | Dòng `To: annie@…` ở trên, `text-meta` | Dòng "Visible to your team only", `text-meta` màu `note-ink` |

### 9.3 Hiển thị trong dòng thời gian
- Tin nhắn công khai: kiểu §8 (không nền).
- Ghi chú nội bộ: khối `rounded-md border border-note-border bg-note px-3 py-2`, icon `Lock` 12px ở cạnh tên, nhãn nhỏ "Internal note" `text-meta` màu `note-ink` sau timestamp.
- Màu vàng **chỉ** dành cho ghi chú nội bộ. Không dùng cho cảnh báo, không dùng cho SLA.

### 9.4 An toàn
- Nội dung chưa gửi của mỗi tab được **giữ riêng**; đổi tab không làm mất bản nháp.
- Không bao giờ tự chuyển từ Internal note sang Reply sau khi gửi; sau khi gửi note, giữ nguyên tab Internal note.
- Khi composer ở chế độ Reply và nội dung bắt đầu bằng `@` đồng nghiệp, hiện cảnh báo nhẹ "Khách hàng sẽ thấy tin này", `text-meta`.

---

## 10. Icon

- Thư viện: **lucide-react** (đã đi kèm shadcn). Chỉ import icon cụ thể.
- Kích thước: 14px (trong badge), 16px (hành động, đầu dòng), 20px (hiếm, trạng thái rỗng). `strokeWidth={1.5}`.
- Màu: kế thừa `currentColor`; mặc định `muted-foreground` hoặc `faint`. Chỉ 3 icon được phép có màu riêng: reply (`action-reply`), priority (`priority-high`), diamond tier.
- Logo công ty và icon nguồn (Slack, Instagram) dùng bản gốc nhiều màu, đặt trong khung 24px/14px, `rounded-sm`.
- Không dùng icon lấp đầy (filled) lẫn với icon nét, không dùng emoji trong UI chrome.

---

## 11. Chuyển động

| Tình huống | Hiệu ứng | Thời lượng |
|---|---|---|
| Mở/đóng popover, dialog | fade + scale 0.98 → 1 | 120–150ms, `ease-out` |
| Đổi tab Reply/Note | đổi màu tức thì, nền composer chuyển 120ms | 120ms |
| Hover hàng | đổi màu nền | 80ms |
| Đếm ngược SLA | đổi số, **không** hoạt ảnh | — |
| Hàng mới đến | nền `muted` mờ dần về trong 1.2s | 1200ms, 1 lần |

Bắt buộc tôn trọng `prefers-reduced-motion` (tắt mọi thứ ngoài đổi màu).

---

## 12. Trạng thái rỗng, tải, lỗi

- **Rỗng:** icon 20px `faint`, một dòng `text-body` nói điều người dùng làm tiếp theo (ví dụ "Chưa có ticket ưu tiên cao. Bạn có thể xem nhóm Medium."), tối đa 1 nút `outline`. Không minh họa, không emoji.
- **Tải:** skeleton có **cùng chiều cao hàng 72px**, nền `muted`, radius 4px, không shimmer. Không spinner toàn trang.
- **Lỗi:** dòng chữ trong khung `border-destructive/30 bg-destructive/5`, nói rõ lỗi gì và cách khắc phục, không xin lỗi, không "Oops".
- Văn bản: sentence case, động từ rõ ràng ("Send reply", "Add note", "Assign to me"), một hành động giữ **cùng tên** xuyên suốt luồng (nút "Add note" → toast "Note added").

---

## 13. Khả năng truy cập & đáp ứng

- Tương phản chữ `foreground` / `card` ≥ 4.5:1 (đạt). `faint` chỉ dùng cho thông tin phụ không thiết yếu; **không** dùng cho nội dung bắt buộc đọc.
- Focus nhìn thấy được trên mọi phần tử tương tác (`ring-2 ring-ring`).
- Bảng queue dùng `role="grid"`/`row`/`gridcell`, hỗ trợ `↑ ↓` chuyển hàng, `Space` chọn, `Enter` mở, `E` gán, `R` trả lời.
- Badge SLA luôn kèm văn bản (không chỉ màu): `aria-label="SLA còn 13 phút 22 giây, khẩn cấp"`.
- Dưới `lg`: ẩn panel phải (mở bằng `Sheet`); dưới `md`: chỉ một cột tại một thời điểm, điều hướng kiểu stack. Vùng chạm tối thiểu 36px trên mobile (tăng `h-8` → `h-9`).

---

## 14. ANTI-PATTERNS: CẤM TUYỆT ĐỐI

Nếu đầu ra của bạn vi phạm bất kỳ mục nào dưới đây, **viết lại** trước khi trả về.

### 14.1 Bề mặt, viền, bóng
- ❌ `shadow-sm/md/lg/xl/2xl` trên card, hàng, input, nút, badge. (Chỉ popover/dialog dùng bóng đã định nghĩa ở §2.4.)
- ❌ Bóng chồng lớp, bóng màu, glow, `drop-shadow-*`, `ring` làm viền trang trí.
- ❌ Card lồng card lồng card. Một bề mặt trắng = một khung viền 1px.
- ❌ Chia nội dung thành các thẻ rời, giống hệt nhau, cách nhau 24px+ (kiểu lưới "feature card" của landing page). Danh sách ticket là **một bảng liền mạch** với đường kẻ.
- ❌ Một giá trị `rounded-*` cho mọi thứ (ví dụ `rounded-2xl` khắp nơi). Dùng thang ở §2.4.
- ❌ Nền gradient, glassmorphism trên nội dung, `backdrop-blur` ngoài overlay.

### 14.2 Màu
- ❌ Gradient ở bất kỳ đâu (nền, nút, chữ, viền).
- ❌ Nền kem/be đậm, accent đất nung (terracotta), accent tím/indigo mặc định của shadcn, hoặc "xanh SaaS" làm màu chủ đạo.
- ❌ Chế độ tối đen kịt (#000/#0B0B0B) + accent xanh neon hoặc cam rực.
- ❌ Tô nền badge tier bằng màu (xanh/lục/vàng). Tier chỉ có diamond màu.
- ❌ Dùng `text-gray-500`, `bg-slate-50`, `border-zinc-200`… trực tiếp. Chỉ dùng token.
- ❌ Đỏ tươi / nhấp nháy / pulse cho SLA. Một tông đào duy nhất cho "khẩn cấp".
- ❌ Dùng màu vàng cho thứ khác ngoài Internal note.

### 14.3 Chữ
- ❌ Chữ IN HOA, `tracking-widest`, eyebrow nhỏ phía trên tiêu đề, nhãn kiểu `LABEL — mô tả`.
- ❌ Font mono cho nhãn dữ liệu nhỏ, trừ khi hiển thị mã/ID kỹ thuật.
- ❌ Thêm cỡ chữ ngoài 13/15px trong vùng làm việc; tiêu đề `text-2xl/3xl` trong bảng, popover, panel.
- ❌ Nhấn **một từ** bằng màu/in nghiêng/in đậm trong tiêu đề.
- ❌ Chuỗi meta nối bằng dấu chấm giữa (`A · B · C`) và mũi tên `→` gắn vào nút/link.
- ❌ Dùng `#000` cho chữ. Dùng `foreground` (#17181C).
- ❌ Số nhảy khi cập nhật: luôn `tabular-nums` cho SLA, ID, bộ đếm.

### 14.4 Bố cục & mật độ
- ❌ Hero, banner, khối thống kê "big number + gradient", biểu đồ trang trí trong màn hình làm việc.
- ❌ Padding khổng lồ (`p-8+`, `py-12+`), hàng cao > 80px, khoảng cách giữa hàng > 0 (hàng liền nhau, ngăn bằng đường kẻ).
- ❌ Căn giữa nội dung làm việc. Mọi thứ canh trái, bám lưới 4px.
- ❌ Sidebar rộng với logo to và menu có icon màu mè. Điều hướng gọn, chữ 15px, icon xám 16px.
- ❌ Hiển thị mọi thông tin cùng lúc ở cỡ lớn. Ưu tiên dòng chính + dòng badge như §4.2.

### 14.5 Component & tương tác
- ❌ Giữ nguyên `Button`, `Badge`, `Tabs`, `Card`, `Dialog` mặc định của shadcn mà không ghi đè theo §7.
- ❌ Nút chính màu xanh/tím; nút chính là mực đen.
- ❌ `hover:scale-*`, `hover:-translate-y-*`, `transition-all` với bóng, `animate-pulse` trang trí, `animate-bounce`, hiệu ứng fade-up khi tải từng khối.
- ❌ Bong bóng chat (nền xám/xanh, đuôi, bo tròn lớn) cho tin nhắn. Tin nhắn là dòng chữ có avatar, không khung.
- ❌ Toast/Alert nhiều màu, icon tròn tô màu to. Toast: nền `card`, viền 1px, 1 dòng.
- ❌ Overlay đen 50%. Overlay là `--scrim` sáng.
- ❌ Emoji làm icon, minh họa SVG "người dùng vui vẻ", ảnh stock, mascot trong trạng thái rỗng.
- ❌ Lẫn lộn Reply công khai và Internal note về mặt thị giác (dùng cùng nền/nút). Chúng **phải** khác biệt như §9.2.

### 14.6 Nội dung chữ
- ❌ Câu từ marketing ("Supercharge your support", "Seamless", "Powerful"), "Oops!", "Something went wrong" không kèm cách xử lý.
- ❌ Nút "Submit", "OK", "Click here". Dùng động từ cụ thể.
- ❌ Dữ liệu giả kiểu "Lorem ipsum", "John Doe", "Acme Inc". Dùng dữ liệu thật hoặc tên/ticket thực tế.

---

## 15. Checklist trước khi hoàn tất mỗi component

- [ ] Chỉ dùng token màu (không có `gray-*`, `slate-*`, `#hex` rải rác).
- [ ] Không có `shadow-*` (trừ lớp nổi); phân tách bằng viền 1px.
- [ ] Chỉ có cỡ chữ 15px / 13px; số có `tabular-nums`.
- [ ] Radius đúng thang (4 / 6 / 8 / 10 / 12 / full cho avatar).
- [ ] Chiều cao hàng 72–74px; badge cao 24px; nút cao 32px.
- [ ] Mỗi hàng không quá 3 màu khác nhau; màu chỉ mang thông tin.
- [ ] Không có gradient, glow, scale-on-hover, animation trang trí.
- [ ] Đã ghi đè component shadcn theo §7.
- [ ] SLA, tier, topic hiển thị đúng kiểu badge ở §5.
- [ ] Reply và Internal note khác biệt rõ rệt, bản nháp giữ riêng từng tab.
- [ ] Có focus ring, nhãn `aria`, tôn trọng `prefers-reduced-motion`.
- [ ] Nhìn thoáng qua: có giống một *công cụ làm việc tĩnh, chính xác* kiểu Plain/Linear, không giống một *trang web mẫu*?

---

## 16. Tham chiếu nhanh (cheat sheet)

```
Nền app        #F4F3F1     Card/Popover   #FFFFFF
Mực            #17181C     Mực phụ        #6B6F77     Mực mờ  #9A9EA5
Viền           #E7E6E2     Kẻ hàng        #EFEEEA     Viền input #E2E1DD
SLA khẩn       #F8B99D / #3A1D0E          SLA thường #E7E7EA / #3B3E45
Tier           ◆ #3B7BEA (Enterprise)  ◆ #2FC98E (Pro)  ◆ #9A9EA5 (Free)
Reply icon     #3B6FE0     Priority High  #EE9B3B
Internal note  nền #FFF8E5  viền #F0E1AE  chữ #6B5410

Chữ            15px/22 (400, 500)  ·  13px/18 (400, 500)
Radius         4 checkbox · 6 badge/nút/logo · 8 input · 10 card · 12 popover
Hàng queue     72–74px   Badge 24px   Nút 32px   Avatar 24px   Icon 14/16px
Cột            340px | flex-1 (max 760px) | 300px
Bóng           chỉ popover: 0 8px 24px -4px rgba(23,24,28,.10)
```