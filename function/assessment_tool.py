# -*- coding: utf-8 -*-
"""評估文字工具（不需登入，貼入評估內容自動產生兩版文字）。"""

import re

import streamlit as st

from function.ui_common import step


def render(backend_email, backend_password, env):
    step("3", "貼入原始評估內容")
    st.markdown(
        '<div class="info-strip">'
        '自動從「建議M人N小時」解析人數與時數，計算平日（×600）與週末（×700）金額，'
        '產生兩個版本供複製使用。不需登入。'
        '</div>',
        unsafe_allow_html=True
    )

    raw = st.text_area("原始評估內容", height=300,
                        placeholder="Alan(台北)\n建議2人6保留加時可能\n10p以下0.5\n...")

    if st.button("產生兩版文字", use_container_width=True):
        if not raw.strip():
            st.warning("請先貼入評估內容")
            st.stop()

        lines = raw.strip().split("\n")
        header_line = ""; recommend_line = ""
        item_lines = []; note_lines = []; sum_line = ""
        phase = "header"

        for i, line in enumerate(lines):
            trimmed = line.strip()
            if not trimmed: continue
            if phase == "header" and i == 0:
                header_line = trimmed; phase = "recommend"; continue
            if phase == "recommend":
                if "建議" in trimmed:
                    # 建議可能夾在長句後半（如「...，建議3人8保留加時可能」），
                    # 從「建議」開始截取，丟掉前面的說明文字
                    idx = trimmed.index("建議")
                    recommend_line = trimmed[idx:]
                    phase = "items"
                # 其他行（@Jenny、說明文字等）在 recommend 階段直接略過
                continue
            if phase == "items":
                if re.match(r"^[\d.+\s]+=", trimmed):
                    sum_line = trimmed; phase = "notes"; continue
                item_lines.append(trimmed); continue
            if phase == "notes":
                note_lines.append(line)

        m = re.search(r"建議\s*(\d+)\s*人\s*(\d+(?:\.\d+)?)", recommend_line)
        extra_lines = []
        if m:
            people = float(m.group(1))
            hours  = float(m.group(2))
            wd_price = int(round(people * hours * 600))
            wk_price = int(round(people * hours * 700))

            # 服務金額（含稅）
            amount_line = f"服務金額：平日 ${wd_price}（含稅）；週末 ${wk_price}（含稅）"

            # 服務時間：依時數規則
            M = int(people)
            N = hours
            hrs_label = int(N) if N == int(N) else N
            time_label = f"{M}人{hrs_label}小時"

            if N <= 3:
                # 短班：AM 09 開始，PM 14 開始，各 N 小時
                am_end = int(9 + N)
                pm_end = int(14 + N)
                time_range = f"09-{am_end:02d}點 或 14-{pm_end:02d}點"
            elif N == 4:
                # 4 小時：AM 08:30 起，PM 14:00 起
                time_range = "08:30-12:30 或 14:00-18:00"
            else:
                # 5 小時以上：09 開始，加 1 小時休息
                end_raw = 9 + N + 1
                end_h   = int(end_raw)
                end_m   = int(round((end_raw - end_h) * 60))
                end_str = f"{end_h:02d}" if end_m == 0 else f"{end_h:02d}:{end_m:02d}"
                time_range = f"09-{end_str}點，中間休息1小時"

            time_line = f"服務時間：{time_label}--{time_range}"
            extra_lines = [amount_line, time_line]

            st.success(
                f"解析：{M} 人 × {hrs_label} 小時 → "
                f"平日 ${wd_price}（含稅）、週末 ${wk_price}（含稅）｜{time_range}"
            )
        else:
            st.warning("未能從建議行解析到「M人N小時」，服務金額與時間欄位略過")

        rec_line = re.sub(
            r"(建議\s*\d+\s*人\s*)(\d+(?:\.\d+)?)(?!小時)",
            lambda mo: mo.group(1) + mo.group(2) + "小時",
            recommend_line
        )

        # 版本一：header + 建議 + 服務金額 + 服務時間 + 空行 + 評估內容: + 項目（含時數）+ 加總
        v1_lines = [header_line, rec_line] + extra_lines + ["", "評估內容："] + item_lines
        if sum_line: v1_lines.append(sum_line)

        # 版本二：header + 建議 + 服務金額 + 服務時間 + 空行 + 評估內容: + 項目（去時數）+ 注意事項（不含加總）
        v2_item_lines = [re.sub(r"[\d.]+\s*$", "", l).rstrip() for l in item_lines]
        v2_lines = [header_line, rec_line] + extra_lines + ["", "評估內容："] + v2_item_lines
        if note_lines:
            v2_lines.append("")
            v2_lines.extend(note_lines)

        st.session_state["assess_v1"] = "\n".join(v1_lines)
        st.session_state["assess_v2"] = "\n".join(v2_lines)

    if st.session_state.get("assess_v1"):
        import html as _html
        import streamlit.components.v1 as _components

        def _copyable_editor(label, content, key_suffix, height):
            safe = _html.escape(content)
            lines = content.count("\n") + 1
            ta_height = max(height, lines * 26 + 60)
            _components.html(f"""
<html><body style="margin:0;padding:0;background:transparent;">
<p style="margin:0 0 4px 0;font-size:14px;font-weight:700;
   font-family:'Noto Sans TC',sans-serif;color:#1C1C1E;">{_html.escape(label)}</p>
<textarea id="ta_{key_suffix}"
  style="width:100%;height:{ta_height}px;box-sizing:border-box;
         border-radius:12px;border:1.5px solid #E8E8EC;
         font-size:14px;line-height:1.6;padding:10px;
         font-family:'Noto Sans TC',sans-serif;resize:vertical;">{safe}</textarea>
<button id="btn_{key_suffix}"
  onclick="navigator.clipboard.writeText(document.getElementById('ta_{key_suffix}').value)
           .then(function(){{
               document.getElementById('btn_{key_suffix}').textContent='✅ 已複製！';
               setTimeout(function(){{
                   document.getElementById('btn_{key_suffix}').textContent='複製';
               }}, 1500);
           }});"
  style="background:#F5C518;border:none;border-radius:12px;padding:9px 16px;
         font-weight:700;cursor:pointer;width:100%;margin-top:8px;font-size:15px;
         font-family:'Noto Sans TC',sans-serif;">
  複製
</button>
</body></html>
""", height=ta_height + 80)

        st.markdown("---")
        step("4", "版本一 — 含時數（至加總）")
        _copyable_editor("版本一", st.session_state["assess_v1"], "v1", 260)

        st.markdown("<div style='margin-top:1.2rem'></div>", unsafe_allow_html=True)
        step("5", "版本二 — 移除時數（含注意事項）")
        _copyable_editor("版本二", st.session_state["assess_v2"], "v2", 600)

