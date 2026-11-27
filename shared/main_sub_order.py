# -*- coding: utf-8 -*-
"""主單＋補單（大單一次刷卡）。

客人總人時很大時（例：30 人時、34 人時），為了讓客人只刷一次卡：
1. 主單：例 4人8小時，其中 K 位放檸檬人（檸檬人的時數由補單補），
   可用「依人時建立優惠券」折抵（例：折 1人2小時 → 付 30 人時）。
   成單時還沒排班可先放多位（甚至全部）檸檬人，再由排班人員置換；
   檸檬人人時必須少於主單＋補單人時。
2. 補單：實際出班的人數／時段，每張用優惠券折到 0 → 已付款＋不開立發票。
3. 備註：主單＋各補單客人備註寫「A＋B＋C合併訂單，2人-09-12點＋3人-09-18點＋1人-14-18點」（每個時段幾人），
   有檸檬人的訂單（主單）客服備註 **X-X** 後加「檸檬人勿動」（沿用 _update_merge_notes）。

純計算函式（summarize_plan／build_merge_note）不連後台，方便測試。
"""
from __future__ import annotations

import re
from datetime import date

from service_pricing import account_balance, customer_tier, load_config, unit_price as service_unit_price

CLEAN_TYPE_ID_BY_LABEL = {
    "居家清潔": "1", "辦公室清潔": "2", "裝修細清": "3", "搬出清潔": "3", "搬入清潔": "3",
}


def _int(value, default=0):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return default


def summarize_plan(main_person, main_hour, lemon_count, coupon_person_hours, subs, placeholder_count=None):
    """主單＋補單人時試算。

    lemon_count：主單現在放幾位檸檬人（成單時還沒排班可放多位、甚至全部，排班人員之後再置換）。
    placeholder_count：其中幾位是「佔位」——時數由補單補、不會有人去上班（預設 1，不可超過檸檬人數）。
    付費人時＝主單人時－優惠人時；實際出班＝(主單人數－佔位)×時數＋補單人時；
    贈送人時＝實際出班－付費人時。檸檬人人時必須少於主單＋補單人時。
    回傳 dict（errors 有內容就不可送出）。
    """
    main_person, main_hour = _int(main_person), _int(main_hour)
    lemon_count, coupon_ph = _int(lemon_count), _int(coupon_person_hours)
    placeholder = min(1, lemon_count) if placeholder_count is None else _int(placeholder_count)
    errors = []
    if main_person <= 0 or main_hour <= 0:
        errors.append("主單人數／時數讀取不到")
    if lemon_count < 0 or (main_person and lemon_count > main_person):
        errors.append("主單檸檬人數必須介於 0 和主單人數之間")
    if placeholder < 0 or placeholder > lemon_count:
        errors.append("佔位人數不可超過主單檸檬人數")
    main_ph = main_person * main_hour
    if coupon_ph < 0 or (main_ph and coupon_ph >= main_ph):
        errors.append("優惠人時必須介於 0 和主單人時之間")
    sub_rows = []
    for i, s in enumerate(subs or [], start=1):
        p, h = _int(s.get("person")), _int(s.get("hour"))
        if p <= 0 or h <= 0:
            errors.append(f"補單{i} 人數／時數必須大於 0")
        sub_rows.append(p * h)
    if not sub_rows:
        errors.append("至少要有 1 筆補單")
    sub_ph = sum(sub_rows)
    lemon_ph = lemon_count * main_hour
    total_ph = main_ph + sub_ph
    if not errors and lemon_ph >= total_ph:
        errors.append(f"檸檬人 {lemon_ph} 人時必須少於主單＋補單 {total_ph} 人時")
    paid_ph = main_ph - coupon_ph
    main_real_ph = max(main_person - placeholder, 0) * main_hour
    actual_ph = main_real_ph + sub_ph
    gift_ph = actual_ph - paid_ph
    if not errors and gift_ph < 0:
        errors.append(f"實際出班 {actual_ph} 人時少於客人付費 {paid_ph} 人時，請確認佔位人數或補單")
    return {
        "main_ph": main_ph, "coupon_ph": coupon_ph, "paid_ph": paid_ph,
        "lemon_ph": lemon_ph, "placeholder": placeholder, "main_real_ph": main_real_ph,
        "sub_ph": sub_ph, "total_ph": total_ph, "actual_ph": actual_ph, "gift_ph": gift_ph,
        "errors": errors,
    }


def _period_bounds(period_s):
    m = re.match(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", str(period_s or ""))
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))


def period_note_text(period_s):
    """09:00-12:00 → 09-12點；08:30-12:30 → 08:30-12:30點。"""
    b = _period_bounds(period_s)
    if not b:
        return str(period_s or "")
    def _t(hm):
        return f"{hm[0]:02d}" if hm[1] == 0 else f"{hm[0]:02d}:{hm[1]:02d}"
    return f"{_t(b[0])}-{_t(b[1])}點"


def build_merge_note(main_order_no, sub_order_nos, main_person, main_period_s, placeholder_count, subs):
    """例：LC00221473＋LC00221474＋LC00221475合併訂單，2人-09-12點＋3人-09-18點＋1人-14-18點。

    列出每個時段實際有幾人（主單扣掉佔位檸檬人；同時段人數加總），依時段先後排序，讓客人知道每個時段幾人。
    """
    nos = sorted({str(x) for x in [main_order_no, *(sub_order_nos or [])] if str(x or "").strip()})
    counts = {}
    main_real = _int(main_person) - _int(placeholder_count)
    if main_real > 0:
        counts[main_period_s] = counts.get(main_period_s, 0) + main_real
    for s in subs or []:
        counts[s.get("period_s")] = counts.get(s.get("period_s"), 0) + _int(s.get("person"))
    order = sorted(counts, key=lambda p: _period_bounds(p) or ((99, 0), (99, 0)))
    return "＋".join(nos) + "合併訂單，" + "＋".join(f"{counts[p]}人-{period_note_text(p)}" for p in order)


def coupon_amount_for_person_hours(service_date, person_hours, tier):
    """優惠券金額＝該服務日期計價等級的每人時單價（含稅）× 人時。"""
    return int(service_unit_price(service_date, tier)) * _int(person_hours)


# ---------------------------------------------------------------------------
# 後台動作
# ---------------------------------------------------------------------------

def _slot_current_names(slots, origin_ids):
    """排班修改頁每個槽位目前的人：用 originShiftId 反查該槽位選項的姓名。"""
    names = []
    for slot_map, origin_id in zip(slots, origin_ids):
        found = ""
        for label, shift_id in (slot_map or {}).items():
            if str(shift_id) == str(origin_id):
                found = label.strip()
                break
        names.append(found)
    return names


def ensure_main_order_lemons(session, base_url, order_no, service_date, period_s, lemon_count,
                             allow_auto_lemon_shift=True):
    """主單維持 lemon_count 位檸檬人，其他槽位（真的要上班的專員）不動。

    - 已有剛好 lemon_count 位 → 不動。
    - 檸檬人多於 lemon_count（正式專員不足）→ 不動，回傳警告。
    - 少於 → 從最後面的正式專員槽位換成可用檸檬人（未配班、未被重疊訂單占用），
      排班頁沒有可用檸檬人且 allow_auto_lemon_shift 才補勾檸檬人班表。
    """
    import quick_order as qo

    lemon_count = _int(lemon_count)
    purchase_id = qo._fetch_order_edit_id(session, order_no)
    if not purchase_id:
        return {"success": False, "message": f"無法取得主單 {order_no} 的後台 ID"}
    csrf, origin_ids, slots = qo._get_schedule_edit_info(session, base_url, service_date, purchase_id)
    if not csrf or not origin_ids or len(origin_ids) != len(slots):
        return {"success": False, "message": "無法讀取主單排班修改頁，請至後台手動處理檸檬人"}
    current = _slot_current_names(slots, origin_ids)
    if any(not n for n in current):
        return {"success": False, "message": "主單排班頁有槽位讀不到目前人員，為避免換錯人已停止，請至後台手動處理"}
    lemon_idx = [i for i, n in enumerate(current) if "檸檬人" in n]
    if len(lemon_idx) == lemon_count:
        return {"success": True, "changed": [], "current": current, "message": f"主單已有 {lemon_count} 位檸檬人，不需調整"}
    if len(lemon_idx) > lemon_count:
        return {"success": True, "changed": [], "current": current,
                "message": f"⚠️ 主單目前有 {len(lemon_idx)} 位檸檬人（多於設定的 {lemon_count} 位，正式專員不足），請確認補單人時"}

    need = lemon_count - len(lemon_idx)
    targets = [i for i in range(len(current) - 1, -1, -1) if i not in lemon_idx][:need]

    def _lemon_no(name):
        m = re.search(r"檸檬人\s*(\d+)", str(name or ""))
        return int(m.group(1)) if m else 9999

    def _pick(slots_now):
        unassigned = set(qo._get_unassigned_staff_for_period(session, base_url, service_date, period_s).get("names") or set())
        occupied = qo._get_occupied_staff_for_period(session, base_url, service_date, period_s, exclude_purchase_id=purchase_id)
        used = {qo._staff_name_key(current[i]) for i in lemon_idx}
        picks = {}
        for i in targets:
            cands = sorted(
                [(k.strip(), v) for k, v in (slots_now[i] or {}).items()
                 if "檸檬人" in k and qo._staff_name_key(k) not in used
                 and qo._staff_name_key(k) not in occupied and qo._staff_name_key(k) in unassigned],
                key=lambda x: _lemon_no(x[0]),
            )
            if cands:
                picks[i] = cands[0]
                used.add(qo._staff_name_key(cands[0][0]))
        return picks

    try:
        picks = _pick(slots)
        if len(picks) < len(targets) and allow_auto_lemon_shift:
            qo.ensure_lemon_cleaner_shifts(
                session=session, base_url=base_url, service_date=service_date,
                period_s=period_s, person_count=str(len(targets) - len(picks)),
            )
            csrf, origin_ids, slots = qo._get_schedule_edit_info(session, base_url, service_date, purchase_id)
            if not csrf or len(origin_ids) != len(current):
                return {"success": False, "message": "補勾檸檬人後無法重讀主單排班頁，請至後台手動處理"}
            picks = _pick(slots)
    except Exception as exc:
        return {"success": False, "message": f"無法確認未配班人力，已停止換檸檬人：{exc}"}
    if len(picks) < len(targets):
        return {"success": False, "message": f"主單需要再換 {len(targets)} 位檸檬人，但只找到 {len(picks)} 位可用檸檬人，請至後台手動處理"}

    fields = [("_token", csrf), ("_method", "PUT")]
    expected = []
    for oid in origin_ids:
        fields.append(("originShiftId[]", str(oid)))
    for j, oid in enumerate(origin_ids):
        sid = str(picks[j][1]) if j in picks else str(oid)
        fields.append((f"shiftId[{j}]", sid))
        expected.append(sid)
    resp = session.post(
        f"{base_url}/schedule/edit", params={"date": service_date, "purchase_id": purchase_id},
        data=fields, headers=qo.HEADERS, allow_redirects=True,
    )
    if resp.status_code not in (200, 302):
        return {"success": False, "message": f"主單換檸檬人失敗：HTTP {resp.status_code}"}
    _c, origin_after, _s = qo._get_schedule_edit_info(session, base_url, service_date, purchase_id)
    if [str(x) for x in origin_after] != expected:
        return {"success": False, "message": "主單換檸檬人已送出，但重讀後未確認到結果，請立即至後台檢查"}
    changed = [f"{current[i]}→{picks[i][0]}" for i in sorted(picks)]
    return {"success": True, "changed": changed, "message": "主單已換檸檬人：" + "、".join(changed)}


def read_main_order(env_name, backend_email, backend_password, order_no):
    """讀主單：日期、時段、人時、地址、電話、付款、發票、會員（補單沿用）。"""
    import requests
    import quick_order as qo
    from orders import get_region_by_address
    from accounts import ACCOUNTS

    base_url = qo._configure_environment(env_name)
    session = requests.Session()
    if not qo.login(session, backend_email, backend_password):
        raise Exception("後台登入失敗，請確認帳號密碼")
    block = qo._fetch_purchase_block_for_order_no(session, order_no)
    lines = block.get("lines", [])
    if not lines:
        raise Exception(f"查不到主單 {order_no}")
    joined = "\n".join(lines)
    service_date, period_raw = qo._parse_service_date_time_loose(joined)
    address = qo._extract_address_line(lines)
    phone = qo._extract_phone_from_block_lines(lines)
    payway = qo.normalize_booking_payway(qo._extract_payway_line(joined))
    person, hour = qo._extract_person_hour_line(joined)
    label = qo._extract_service_type_label(lines) or "居家清潔"
    clean_type_id = CLEAN_TYPE_ID_BY_LABEL.get(label, "1")
    if not (service_date and address and phone):
        raise Exception(f"主單 {order_no} 讀不到服務日期／地址／電話")
    if not payway:
        raise Exception(f"主單 {order_no} 付款方式解析失敗")
    token = qo.get_csrf_token(session)
    member_payload = qo.get_member(session, phone, token, clean_type_id)
    if not member_payload:
        raise Exception(f"電話 {phone} 查無會員資料")
    member_email = (member_payload.get("member", {}) or {}).get("email", "")
    return {
        "session": session, "base_url": base_url, "env_name": env_name, "order_no": order_no,
        "service_date": service_date, "period_s": str(period_raw or "").replace(" ", ""),
        "person": _int(person), "hour": _int(hour), "address": address, "phone": phone,
        "payway": payway, "region": get_region_by_address(address, ACCOUNTS) or "台北",
        "service_label": label, "clean_type_id": clean_type_id, "member_payload": member_payload,
        "lookup_result": {"session": session, "token": token, "phone": phone, "member_payload": member_payload,
                          "base_url": base_url, "env_name": env_name},
        "invoice_kwargs": qo._invoice_kwargs_from_block(lines, member_email),
    }


def _pricing_tier(member_payload):
    if not load_config()["enabled"]:
        return "regular"
    return customer_tier("existing", account_balance(member_payload))


def create_sub_orders(ctx, subs):
    """補單：每張建優惠券＝全額 → 建單 → 總金額扣車馬費為 0 時標已付款＋不開立發票。"""
    import quick_order as qo

    session, base_url = ctx["session"], ctx["base_url"]
    tier = _pricing_tier(ctx["member_payload"])
    today_str = date.today().strftime("%Y-%m-%d")
    results = []
    for idx, sub in enumerate(subs, start=1):
        d, period_s = sub["date_s"], sub["period_s"]
        person, hour = str(_int(sub["person"])), str(_int(sub["hour"]))
        try:
            price = coupon_amount_for_person_hours(d, _int(person) * _int(hour), tier)
            prefix = qo._coupon_prefix(ctx["region"], f"s{ctx['order_no'][-3:]}{idx}")

            def _make_coupon(price=price, prefix=prefix, d=d):
                code = qo._build_coupon_via_session(
                    session, base_url,
                    title=qo._coupon_title(ctx["member_payload"], ctx["order_no"], amount=price),
                    discount=price, date_s=today_str, date_e=d, prefix=prefix, piece=1,
                    regions=[ctx["region"]], service_items=[ctx["service_label"]],
                )
                if not code:
                    raise Exception(f"補單優惠券建立失敗（prefix={prefix}，金額={price}），未送出補單")
                return code

            res = qo.quick_create_order(
                env_name=ctx["env_name"], payway=ctx["payway"], region=ctx["region"],
                lookup_result=ctx["lookup_result"], address=ctx["address"],
                clean_type_id=ctx["clean_type_id"], date_s=d, period_s=period_s,
                hour=hour, person=person, discount_code=_make_coupon, pricing_tier=tier,
                allow_auto_lemon_shift=bool(sub.get("allow_lemon")),
                **({} if ctx["payway"] == "儲值金" else (ctx.get("invoice_kwargs") or {})),
            )
            due, paid_ok, paid_msg, inv_ok, inv_msg = qo.settle_zero_due_order(session, base_url, res["order_no"])
            results.append({
                "index": idx, "order_no": res["order_no"], "date_s": d, "period_s": period_s,
                "person": person, "hour": hour, "price": price, "coupon_code": res.get("discount_code", ""),
                "staff": res.get("staff", ""), "service_due": due,
                "paid_ok": paid_ok, "paid_msg": paid_msg, "invoice_ok": inv_ok, "invoice_msg": inv_msg,
                "error": None,
            })
        except Exception as exc:
            results.append({"index": idx, "order_no": None, "date_s": d, "period_s": period_s,
                            "person": person, "hour": hour, "error": str(exc)})
    return results


def run_main_sub(env_name, backend_email, backend_password, main_order_no, lemon_count, subs,
                 coupon_person_hours=0, allow_auto_lemon_shift=True, placeholder_count=None):
    """主單調整檸檬人 → 建補單 → 主單＋補單寫合併備註 → 合併 LINE 訊息。"""
    import quick_order as qo

    ctx = read_main_order(env_name, backend_email, backend_password, main_order_no)
    plan = summarize_plan(ctx["person"], ctx["hour"], lemon_count, coupon_person_hours, subs, placeholder_count)
    if plan["errors"]:
        raise Exception("；".join(plan["errors"]))
    lemon = ensure_main_order_lemons(
        ctx["session"], ctx["base_url"], main_order_no, ctx["service_date"], ctx["period_s"],
        lemon_count, allow_auto_lemon_shift=allow_auto_lemon_shift,
    )
    if not lemon.get("success"):
        raise Exception(f"主單檸檬人調整失敗，未建立補單：{lemon.get('message')}")
    sub_results = create_sub_orders(ctx, subs)
    sub_nos = [r["order_no"] for r in sub_results if r.get("order_no")]
    note = build_merge_note(main_order_no, sub_nos, ctx["person"], ctx["period_s"], plan["placeholder"],
                            [r for r in sub_results if r.get("order_no")])
    note_results = []
    if sub_nos:
        for ono in [main_order_no, *sub_nos]:
            ok, msg = qo._update_merge_notes(ctx["session"], ctx["base_url"], ono, note)
            note_results.append({"order_no": ono, "ok": ok, "msg": msg})
    line_message = ""
    if sub_nos:
        try:
            line_message = qo.build_combined_line_message_from_order_nos(
                env_name, backend_email, backend_password, [main_order_no, *sub_nos],
                fallback_region=ctx["region"], session=ctx["session"],
            )
        except Exception as exc:
            line_message = f"（合併 LINE 訊息產生失敗：{exc}）"
    return {
        "main_order_no": main_order_no, "service_date": ctx["service_date"], "period_s": ctx["period_s"],
        "main_person": ctx["person"], "main_hour": ctx["hour"], "plan": plan,
        "lemon_result": lemon, "sub_results": sub_results, "note": note,
        "note_results": note_results, "line_message": line_message,
    }
