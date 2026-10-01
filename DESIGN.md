# Design System — Face Recognition Attendance System

## 1. Design Direction

Build this like a modern biometric/access-control panel, not a generic SaaS dashboard.
Calm, dark, minimal, confident. Every element must earn its place — no decorative filler.

**Explicitly avoid (these scream "AI generated"):**
- Purple-to-blue gradients
- Glassmorphism everywhere
- Emoji used as icons
- Centered hero text with a gradient blob behind it
- Generic stock illustrations
- Default shadcn purple theme untouched
- Heavy card shadows on every element
- Spinners instead of skeleton loaders

**Aim for instead:**
- Deep neutral background, one accent color used sparingly
- Real icon library (Lucide)
- Intentional layout asymmetry, not everything centered
- Micro-interactions: button press scale, 150–200ms transitions
- Designed empty/loading/error states, not skipped

---

## 2. Color System

Use a neutral base (zinc/slate) + one accent. Do NOT use purple as the accent unless brand-required.

```
Background (base):      #0A0B0D   (near-black, not pure black)
Surface (cards/panels):  #131417
Surface elevated:        #1B1D21
Border subtle:           #26282D
Border strong:           #34363C

Text primary:            #F4F4F5
Text secondary:          #9A9CA3
Text muted:               #5F6167

Accent (pick ONE):       #22D3EE (cyan) OR #34D399 (emerald) OR #FBBF24 (amber)
Accent hover:            10% lighter than accent
Accent muted bg:         accent at 12% opacity, used for badges/pills

Status — used ONLY for these meanings, nowhere else in the UI:
  Present / Matched:      #34D399 (green)
  Pending / Late:         #FBBF24 (amber)
  Absent / Error / No match: #F87171 (red)
```

Rule: status colors are reserved. Never reuse green/amber/red for anything decorative.

---

## 3. Typography

- Single typeface: **Inter** or **Geist**
- Only 2 weights: Regular (400) and Semibold (600). Use Bold (700) sparingly for numbers only.
- Type scale (px): 12, 14, 16, 20, 24, 32, 48
- Line height: 1.5 for body, 1.2 for headings
- Never use decorative/script fonts anywhere

```
Display (dashboard hero numbers): 48px / Semibold
H1 (page title):                  24px / Semibold
H2 (section title):               20px / Semibold
Body:                             14px / Regular
Small / meta text:                12px / Regular
```

---

## 4. Spacing & Layout

Use a strict 4px base spacing scale. No arbitrary padding values.

```
4, 8, 12, 16, 24, 32, 48, 64
```

- Page padding: 32px (desktop), 16px (mobile)
- Card padding: 24px
- Gap between cards/sections: 24px
- Gap between related elements (label + value): 8px
- Border radius: 12px for cards, 8px for buttons/inputs, 999px for pills/badges

---

## 5. Screens

### 5.1 Live Scan / Check-in Screen (primary screen)

- Camera feed: large, centered, 16:9 or 4:3, rounded corners (16px), max-width ~640px
- Thin 2px border around the feed that changes color by state:
  - Idle: border-strong gray
  - Scanning: accent color, subtle pulse animation
  - Matched: green, brief glow
  - Error/No match: red, brief shake (150ms, subtle — not cartoonish)
- Animated scanner overlay: 4 corner brackets (viewfinder style) instead of a full frame. A thin horizontal line sweeps top-to-bottom while state = scanning.
- On match: name, confidence %, and timestamp fade + slide up from bottom of the feed (200ms ease-out). Avoid modal popups — keep it inline and non-blocking.
- On failure states, show icon + short text + color, e.g.:
  - "No face detected" (muted, neutral — not red, this isn't an error)
  - "Multiple faces detected" (amber)
  - "Face not recognized" (red)
- Small status strip below feed: connection status dot (pulsing when live), current time, today's present count

### 5.2 Admin Dashboard

- Hero row: 3–4 stat cards max (Present / Absent / Late / Total) — big number (Display size), label below in text-secondary, tiny trend indicator (▲/▼ + %) only if meaningful
- One chart max above the fold (e.g. today's check-in timeline or weekly attendance trend). Don't stack multiple charts competing for attention.
- Attendance table below:
  - Sticky header
  - Row height ~56px, avatar thumbnail (32px circle) + name + department
  - Status shown as a small pill badge (green/amber/red per system above)
  - Subtle row hover (background lightens by one surface step)
  - Search bar + filter dropdown (department, date range, status) inline above table, left-aligned — not centered
- Real-time pulsing dot next to "Live" label if dashboard auto-updates

### 5.3 Face Enrollment Flow

- Step-by-step capture, one instruction at a time: "Look straight" → "Turn left" → "Turn right" → "Done"
- Progress shown as dots or a thin progress bar at top, not a numbered wizard with heavy borders
- Live camera preview with the same viewfinder-corner style as the scan screen (visual consistency across the app)
- Success state: checkmark draws in (SVG stroke animation, ~400ms), then auto-advances

### 5.4 Reports / History

- Date range picker (custom-styled, not raw browser default)
- Calendar heatmap (GitHub-contributions style) OR simple line chart for attendance trend — pick one, not both
- Exportable table (CSV/PDF button, top-right, secondary button style)

---

## 6. Components

### Buttons
- Primary: solid accent background, dark text if accent is light (amber/cyan), white text if accent is deep. 8px radius. Scale to 0.97 on press (150ms).
- Secondary: transparent bg, 1px border-strong, text-primary. Hover: surface-elevated bg.
- Destructive: red border/text, transparent bg. Solid red only on confirm actions.
- Height: 40px default, 36px compact, 48px for primary CTA on scan screen

### Cards
- Background: surface color, 1px border-subtle, 12px radius
- No heavy drop shadows — if used at all, keep to `0 1px 3px rgba(0,0,0,0.3)` max
- Hover (if interactive): border-strong, slight background lift

### Badges / Status Pills
- 999px radius, 12px text, 4px vertical / 10px horizontal padding
- Background = status color at 12% opacity, text = full status color

### Inputs
- Height 40px, 8px radius, 1px border-subtle, surface-elevated background
- Focus state: 1px accent border + 2px accent glow ring (not default blue browser outline)

### Loading States
- Skeleton loaders (pulsing gray blocks matching final layout shape) for tables/cards — never a spinner for content that has a known shape
- Spinner only acceptable for button-level inline loading (e.g. "Saving...")

### Empty States
- Icon (outline style, muted color) + one line of text + optional action button
- Never leave a blank white/dark space with nothing

---

## 7. Motion Rules

- Standard transition: 150–200ms, ease-out
- Page/section transitions: fade + 8px slide, 200ms
- Never animate more than 2 properties at once (e.g. opacity + transform is fine, don't also animate color + size + position together)
- Scanning animation loop: 1.5–2s per cycle, subtle, not distracting
- Success confirmations get a small celebratory but professional animation (checkmark draw or brief scale bounce, 300–400ms) — nothing bouncy/playful (no confetti, no emoji reactions)

---

## 8. Icons

- Use **Lucide** icon set exclusively (or Phosphor as alternative) — consistent stroke width (1.5–2px) throughout
- No emoji anywhere in the UI, including empty states and notifications
- Icon size: 16px inline with text, 20px in buttons, 24px standalone

---

## 9. Accessibility & States to Explicitly Design (don't skip)

- Loading state
- Empty state (no employees enrolled yet, no attendance today, no search results)
- Error state (camera permission denied, network error, no face detected)
- Success state
- Focus/keyboard navigation states on all interactive elements
- Color contrast: text-secondary on background must meet WCAG AA minimum

---

## 10. Tech/Build Notes for Agents

- Use Tailwind CSS with the color tokens above defined as CSS variables/theme extension — don't use default Tailwind slate/purple defaults untouched
- Component library: shadcn/ui is fine as a base, but override default theme colors, radius, and shadow tokens per this doc
- Icons: `lucide-react`
- Charts: `recharts` (keep charts minimal — no unnecessary gridlines, legends, or tooltips beyond what's needed)
- Fonts: Inter or Geist via next/font or Google Fonts, weights 400 + 600 only
- All interactive elements need hover, active, and focus states defined — do not ship with browser defaults