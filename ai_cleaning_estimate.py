# -*- coding: utf-8 -*-
"""公開版 AI 清潔估時頁面。

設計原則：
1. 不需要登入後台。
2. 照片／影片只在本次 Streamlit session 中處理，不寫入 GitHub。
3. AI 只辨識項目；最終工時由規則引擎與人工確認值計算。
4. 未打開拍攝的櫃內、抽屜一律不納入。
"""
from __future__ import annotations

import base64
import json
import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
import streamlit as st


PHOTO_TYPES = ["jpg", "jpeg", "png", "webp"]
VIDEO_TYPES = ["mp4", "mov", "m4v"]

ROOM_KEYS = {
    "房間": "rooms",
    "衛浴": "bathrooms",
    "廚房": "kitchens",
    "客餐廳": "living_dining",
    "陽台": "balconies",
    "窗戶": "windows",
    "三合一拉門": "sliding_doors",
    "間接照明空間": "indirect_lighting",
    "樓梯": "stairs",
    "車庫": "garages",
}

DEFAULT_VALUES: Dict[str, Any] = {
    "service_type": "裝修細清",
    "ping": 0.0,
    "rooms": 0,
    "rooms_missing_photo": 0,
    "rooms_not_cleaning": 0,
    "bathrooms": 0,
    "kitchens": 0,
    "living_dining": 0,
    "balconies": 0,
    "windows": 0,
    "windows_incomplete": True,
    "sliding_doors": 0,
    "indirect_lighting": 0,
    "stairs": 0,
    "garages": 0,
    "opened_kitchen_cabinets": 0,
    "opened_other_cabinets": 0,
    "opened_drawers": 0,
    "construction_incomplete": False,
    "rough_clean_done": True,
    "loose_items_included": False,
    "notes": "",
}


@dataclass
class EstimateLine:
    label: str
    qty_text: str
    hours: float
    note: str = ""


def _secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default) or default)
    except Exception:
        return os.getenv(name, default)


def _mime_from_name(name: str) -> str:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else "jpeg"
    return {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")


def _to_data_url(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


def extract_video_frames(uploaded_file: Any, every_seconds: int = 4, max_frames: int = 18) -> List[bytes]:
    """以 OpenCV 從影片擷取代表畫面。未安裝時回傳空清單並由 UI 提示。"""
    try:
        import cv2  # type: ignore
    except Exception:
        return []

    suffix = "." + uploaded_file.name.rsplit(".", 1)[-1].lower()
    frames: List[bytes] = []
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(uploaded_file.getvalue())
        path = tmp.name
    try:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        duration = frame_count / fps if fps else 0
        if duration <= 0:
            targets = list(range(max_frames))
        else:
            targets = [min(duration, i * every_seconds) for i in range(max_frames)]
        for sec in targets:
            cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            ok2, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            if ok2:
                frames.append(encoded.tobytes())
        cap.release()
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return frames


def analyze_media_with_openai(image_items: List[Tuple[str, bytes]]) -> Dict[str, Any]:
    """呼叫 OpenAI Responses API；若未設定 API key，會明確報錯。"""
    api_key = _secret("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("尚未設定 OPENAI_API_KEY，請先於 Streamlit Secrets 設定。")
    model = _secret("AI_ESTIMATE_MODEL", "gpt-4.1-mini")

    schema_example = {
        **DEFAULT_VALUES,
        "missing_items": ["第三間房間", "前後陽台窗戶"],
        "photo_findings": ["廚房下櫃已打開", "部分窗戶未拍到完整窗框窗溝"],
        "confidence": 0.0,
    }
    instructions = f"""
你是台灣居家清潔公司的估價照片檢查助手。請只根據畫面中確實看得到的內容輸出 JSON。
重要硬規則：
- 未打開拍攝的櫃內、抽屜，不得計入 opened_kitchen_cabinets、opened_other_cabinets、opened_drawers。
- 看不到完整窗戶、窗框、窗溝或同一組窗戶可能重複出現時，windows_incomplete 必須為 true。
- 缺房間照片、缺窗戶照片、施工中、櫃板仍在切割或可能新增櫃體，都要列入 missing_items/photo_findings。
- 不要自行猜坪數；無法確認填 0。
- 同一空間在多張照片重複出現時不要重複計數。
- 只回傳 JSON，不要 Markdown。
欄位範例：{json.dumps(schema_example, ensure_ascii=False)}
""".strip()

    content: List[Dict[str, Any]] = [{"type": "input_text", "text": instructions}]
    for name, raw in image_items[:30]:
        content.append({"type": "input_text", "text": f"檔案：{name}"})
        content.append({"type": "input_image", "image_url": _to_data_url(raw, _mime_from_name(name))})

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "input": [{"role": "user", "content": content}],
            "temperature": 0.1,
        },
        timeout=180,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"AI 分析失敗（HTTP {response.status_code}）：{response.text[:600]}")
    payload = response.json()
    text = payload.get("output_text", "")
    if not text:
        for item in payload.get("output", []):
            for part in item.get("content", []):
                if part.get("type") in ("output_text", "text"):
                    text += part.get("text", "")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    parsed = json.loads(text)
    result = dict(DEFAULT_VALUES)
    result.update(parsed if isinstance(parsed, dict) else {})
    return result


def ping_hours(ping: float) -> float:
    if ping <= 0:
        return 0.0
    if ping <= 10:
        return 0.25
    if ping <= 20:
        return 0.5
    if ping <= 40:
        return 0.5
    if ping <= 60:
        return 0.75
    if ping <= 80:
        return 0.75
    return 1.0


def build_estimate(values: Dict[str, Any]) -> Tuple[List[EstimateLine], float, List[str], str]:
    """依目前提供案例的裝修細清係數計算人時。"""
    lines: List[EstimateLine] = []
    warnings: List[str] = []

    p = float(values.get("ping") or 0)
    lines.append(EstimateLine("室內坪數", f"{p:g} 坪", ping_hours(p)))

    rooms = max(0, int(values.get("rooms") or 0) - int(values.get("rooms_not_cleaning") or 0))
    room_hours = rooms * 1.0 / 3.0  # 3房約1人時
    missing_rooms = int(values.get("rooms_missing_photo") or 0)
    room_note = ""
    if missing_rooms:
        room_note = f"其中 {missing_rooms} 間缺照片，以標準時間粗估，不含該房窗戶"
        warnings.append("房間照片不完整，缺拍房間僅能以標準時間粗估，且不含未拍攝窗戶。")
    lines.append(EstimateLine("房間", f"{rooms} 間", room_hours, room_note))

    bathrooms = int(values.get("bathrooms") or 0)
    lines.append(EstimateLine("衛浴", f"{bathrooms} 間", bathrooms * 1.5))

    kitchens = int(values.get("kitchens") or 0)
    cabinet_units = int(values.get("opened_kitchen_cabinets") or 0)
    kitchen_hours = kitchens * 1.5 + cabinet_units * 0.3
    kitchen_note = "僅納入已打開並清楚拍攝的廚房櫃內／家電櫃；未打開者不納入"
    lines.append(EstimateLine("廚房", f"{kitchens} 區；已開櫃 {cabinet_units} 單位", kitchen_hours, kitchen_note))

    ld = int(values.get("living_dining") or 0)
    lines.append(EstimateLine("客餐廳", f"{ld} 區", ld * 2.5))

    balconies = int(values.get("balconies") or 0)
    lines.append(EstimateLine("陽台", f"{balconies} 處", balconies * 0.75))

    windows = int(values.get("windows") or 0)
    lines.append(EstimateLine("窗戶", f"{windows} 扇／組", windows * 0.5, "只計目前拍攝且可辨識者"))
    if values.get("windows_incomplete"):
        warnings.append("窗戶照片不完整；未拍攝、未拍到完整窗框／窗溝及前後陽台窗戶均未納入。")

    sliding = int(values.get("sliding_doors") or 0)
    lines.append(EstimateLine("三合一拉門", f"{sliding} 組", sliding * 0.75))

    indirect = int(values.get("indirect_lighting") or 0)
    lines.append(EstimateLine("間接照明", f"{indirect} 空間", indirect * 0.4433))

    stairs = int(values.get("stairs") or 0)
    lines.append(EstimateLine("樓梯", f"{stairs} 層", stairs * 0.3))

    garages = int(values.get("garages") or 0)
    lines.append(EstimateLine("車庫", f"{garages} 車位", garages * 1.0))

    other_cabinets = int(values.get("opened_other_cabinets") or 0)
    drawers = int(values.get("opened_drawers") or 0)
    if other_cabinets or drawers:
        lines.append(EstimateLine("其他已開櫃／抽屜", f"櫃 {other_cabinets}、抽屜 {drawers}", other_cabinets * 0.3 + drawers * 0.18, "只計已打開並清楚拍攝者"))

    total = round(sum(x.hours for x in lines), 2)

    if values.get("construction_incomplete"):
        warnings.append("工程或櫃體尚未完成，後續可能新增櫃體／板材，目前只能暫估，完成後需重新拍攝。")
    if values.get("service_type") == "裝修細清" and not values.get("rough_clean_done"):
        warnings.append("粗清尚未完成，會影響細清時間與成效；建議粗清完成後 3–5 天再安排細清。")

    if values.get("construction_incomplete"):
        status = "暫時估算"
    elif warnings:
        status = "可粗估，需保留加時"
    else:
        status = "照片大致完整，可粗估"
    return lines, total, warnings, status


def suggest_staffing(total_hours: float, construction_incomplete: bool = False) -> Tuple[str, float]:
    if total_hours <= 0:
        return "尚無法建議", 0
    options = []
    for people in (2, 3, 4):
        hours_each = math.ceil((total_hours / people) * 2) / 2
        if 3 <= hours_each <= 8:
            capacity = people * hours_each
            options.append((capacity - total_hours, people, hours_each, capacity))
    if not options:
        people = 4
        hours_each = math.ceil((total_hours / people) * 2) / 2
        return f"{people} 人 × {hours_each:g} 小時", people * hours_each
    _, people, hours_each, capacity = min(options, key=lambda x: (x[0], abs(x[1] - 3)))
    if construction_incomplete:
        hours_each = min(8.0, max(hours_each, 8.0))
        capacity = people * hours_each
    return f"{people} 人 × {hours_each:g} 小時", capacity


def build_customer_text(values: Dict[str, Any], lines: List[EstimateLine], total: float, staffing: str, warnings: List[str]) -> str:
    missing_note = "\n".join(f"- {x}" for x in warnings) if warnings else "- 目前照片大致完整"
    detail = "\n".join(f"{x.label}：{x.qty_text}，{x.hours:g} 人時" + (f"（{x.note}）" if x.note else "") for x in lines if x.hours or x.label in ("房間", "窗戶", "廚房"))
    return f"""目前依提供的照片／影片粗估：建議安排 {staffing}，並保留加時可能。

評估明細：
{detail}
合計：約 {total:g} 人時

需補拍／注意：
{missing_note}

1. 窗戶清潔以窗框、窗溝為主；紗窗若可正常開關且無變形可拆洗，窗戶玻璃及隱形紗窗不拆洗，僅擦拭。
2. 因安全考量，窗外無法安全站立時，僅施作手部可安全擦拭的範圍；非對開窗、景觀窗及外推窗以內側為主。
3. 櫃內及抽屜只納入照片中已打開並清楚拍攝的空間；未打開者不納入。零碎物品、天花板、牆壁、百葉窗、欄杆及其他未列出項目亦未納入。
4. 不承接窗簾清潔及協助搬抬單件超過 10 公斤物品。
5. 現場請準備梯子或可安全踩踏的椅子 2 張、水管及垃圾袋；若無登高設備，高處可能無法完整施作。
6. 本次評估以照片／影片、格局及文字敘述為準；若新增櫃體、裝潢或其他施作項目，可能增加所需時數。
7. 吃色、矽利康發霉、水垢滲入材質等非表面髒污，可能無法完整清除，將由專員現場施作後說明。"""


def render_public_ai_estimate() -> None:
    st.markdown("""
    <div style="background:linear-gradient(135deg,#fffbe8,#ffffff);border:1px solid #f0d76b;border-radius:18px;padding:24px 28px;margin-bottom:20px">
      <div style="font-size:30px;font-weight:800">📷 AI 清潔估時</div>
      <div style="margin-top:6px;color:#555">上傳住宅照片或影片，確認實際拍攝到的空間，再產生清潔人時粗估。此頁不需要登入後台。</div>
    </div>
    """, unsafe_allow_html=True)

    st.warning("估時只依實際拍攝內容：未打開的櫃內／抽屜、未拍到的窗戶與房間一律不納入；照片不足時會要求補拍或標示為暫估。")

    with st.expander("拍攝方式（請先看）", expanded=True):
        st.markdown("""
- 每個房間至少拍「入口往內」及「室內往入口」兩個方向。
- 每組窗戶需拍完整正面、窗框／窗溝、紗窗及窗外安全施作環境。
- 需要清潔櫃內或抽屜時，請把每扇櫃門、每個抽屜打開後拍攝；沒有打開就不會納入。
- 裝修細清請等工程與櫃體完成、裝修垃圾清運及粗清完成後再拍，估時才會較準。
        """)

    photos = st.file_uploader("上傳照片（可多選）", type=PHOTO_TYPES, accept_multiple_files=True, key="ai_est_photos")
    videos = st.file_uploader("上傳影片（可多選）", type=VIDEO_TYPES, accept_multiple_files=True, key="ai_est_videos")

    media_items: List[Tuple[str, bytes]] = []
    for f in photos or []:
        media_items.append((f.name, f.getvalue()))
    frame_count = 0
    for v in videos or []:
        frames = extract_video_frames(v)
        frame_count += len(frames)
        for i, raw in enumerate(frames, 1):
            media_items.append((f"{v.name}-frame-{i}.jpg", raw))
    if videos and frame_count == 0:
        st.info("影片已上傳，但目前環境無法擷取畫面。請在 requirements.txt 加入 opencv-python-headless，或先改上傳影片截圖。")
    if media_items:
        st.caption(f"本次可分析影像：{len(media_items)} 張（含影片擷取畫面 {frame_count} 張）")
        with st.expander("預覽部分影像", expanded=False):
            st.image([raw for _, raw in media_items[:12]], width=180)

    if st.button("✨ AI 分析照片／影片", use_container_width=True, type="primary", disabled=not media_items):
        try:
            with st.spinner("分析空間、窗戶及已打開櫃體中…"):
                st.session_state.ai_estimate_detected = analyze_media_with_openai(media_items)
            st.success("分析完成。請逐項確認，AI 辨識不會直接視為最終數量。")
        except Exception as exc:
            st.error(str(exc))

    detected = dict(DEFAULT_VALUES)
    detected.update(st.session_state.get("ai_estimate_detected") or {})

    st.markdown("### 1. 人工確認基本資料")
    c1, c2, c3 = st.columns(3)
    with c1:
        service_type = st.selectbox("服務類型", ["裝修細清", "搬入／搬出清潔", "居家大掃除"], index=["裝修細清", "搬入／搬出清潔", "居家大掃除"].index(detected.get("service_type", "裝修細清")) if detected.get("service_type") in ["裝修細清", "搬入／搬出清潔", "居家大掃除"] else 0)
    with c2:
        ping = st.number_input("室內坪數", min_value=0.0, max_value=300.0, value=float(detected.get("ping") or 0), step=0.5)
    with c3:
        construction_incomplete = st.checkbox("工程／櫃體尚未完成", value=bool(detected.get("construction_incomplete")))
    rough_clean_done = st.checkbox("裝修垃圾已清運、工程痕跡已粗清並完成第一次吸塵", value=bool(detected.get("rough_clean_done", True)), disabled=service_type != "裝修細清")

    st.markdown("### 2. 確認空間與照片完整度")
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        rooms = st.number_input("房間總數", 0, 20, int(detected.get("rooms") or 0))
        rooms_not_cleaning = st.number_input("其中不需清潔", 0, 20, int(detected.get("rooms_not_cleaning") or 0))
        rooms_missing_photo = st.number_input("缺照片的房間", 0, 20, int(detected.get("rooms_missing_photo") or 0))
    with a2:
        bathrooms = st.number_input("衛浴", 0, 20, int(detected.get("bathrooms") or 0))
        kitchens = st.number_input("廚房", 0, 10, int(detected.get("kitchens") or 0))
        living_dining = st.number_input("客餐廳區域", 0, 10, int(detected.get("living_dining") or 0))
    with a3:
        balconies = st.number_input("陽台", 0, 20, int(detected.get("balconies") or 0))
        windows = st.number_input("目前有完整拍到的窗戶", 0, 100, int(detected.get("windows") or 0))
        windows_incomplete = st.checkbox("窗戶照片不完整／另有未拍窗戶", value=bool(detected.get("windows_incomplete", True)))
    with a4:
        sliding_doors = st.number_input("三合一拉門", 0, 30, int(detected.get("sliding_doors") or 0))
        indirect_lighting = st.number_input("有間接照明的空間", 0, 30, int(detected.get("indirect_lighting") or 0))
        stairs = st.number_input("樓梯層數", 0, 20, int(detected.get("stairs") or 0))
        garages = st.number_input("車庫車位", 0, 20, int(detected.get("garages") or 0))

    st.markdown("### 3. 只計算有打開拍攝的櫃內／抽屜")
    b1, b2, b3 = st.columns(3)
    with b1:
        opened_kitchen_cabinets = st.number_input("廚房已打開櫃內／家電櫃單位", 0, 100, int(detected.get("opened_kitchen_cabinets") or 0), help="未打開或看不清楚內部者請填 0")
    with b2:
        opened_other_cabinets = st.number_input("其他區域已打開櫃內單位", 0, 100, int(detected.get("opened_other_cabinets") or 0))
    with b3:
        opened_drawers = st.number_input("已拉開並拍清楚的抽屜", 0, 200, int(detected.get("opened_drawers") or 0))

    values = {
        "service_type": service_type,
        "ping": ping,
        "rooms": rooms,
        "rooms_not_cleaning": rooms_not_cleaning,
        "rooms_missing_photo": rooms_missing_photo,
        "bathrooms": bathrooms,
        "kitchens": kitchens,
        "living_dining": living_dining,
        "balconies": balconies,
        "windows": windows,
        "windows_incomplete": windows_incomplete,
        "sliding_doors": sliding_doors,
        "indirect_lighting": indirect_lighting,
        "stairs": stairs,
        "garages": garages,
        "opened_kitchen_cabinets": opened_kitchen_cabinets,
        "opened_other_cabinets": opened_other_cabinets,
        "opened_drawers": opened_drawers,
        "construction_incomplete": construction_incomplete,
        "rough_clean_done": rough_clean_done,
    }

    lines, total, warnings, status = build_estimate(values)
    staffing, capacity = suggest_staffing(total, construction_incomplete)

    st.markdown("### 4. 估時結果")
    m1, m2, m3 = st.columns(3)
    m1.metric("估算人時", f"{total:g}")
    m2.metric("建議安排", staffing)
    m3.metric("評估狀態", status)

    st.dataframe(
        [{"項目": x.label, "數量／條件": x.qty_text, "人時": round(x.hours, 2), "說明": x.note} for x in lines],
        use_container_width=True,
        hide_index=True,
    )

    if warnings:
        st.error("目前尚不能視為完整估價：")
        for w in warnings:
            st.write(f"- {w}")
        st.info("請補拍缺少的房間、完整窗戶，以及所有希望清潔且已打開的櫃內／抽屜；補拍後重新分析。")
    else:
        st.success("目前照片大致完整，仍建議現場保留合理加時彈性。")

    customer_text = build_customer_text(values, lines, total, staffing, warnings)
    st.text_area("可複製給客戶的評估文字", customer_text, height=520)
    st.download_button("下載評估文字", data=customer_text.encode("utf-8"), file_name="清潔估時評估.txt", mime="text/plain", use_container_width=True)

    st.caption("隱私說明：本頁程式不會把照片寫入 GitHub。部署時仍應搭配私有暫存空間、檔案刪除期限及正式隱私告知。")
