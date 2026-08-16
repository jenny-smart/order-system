# -*- coding: utf-8 -*-
"""地址解析、行政區驗證工具，供 quick_order.py 建單流程共用。

geocode_address／check_contain 仍留在 orders.py 原地，由呼叫端（quick_order.py）
直接呼叫；這裡只放不連網路的純解析/驗證函式。
"""

import re

from shared.text_parsing import _fix_address_district_order, _normalize_city_for_country_id, _extract_district_from_address, normalize_addr_for_match

COUNTRY_ID_BY_CITY_AREA = {
    ("台北市", "中正區"): "8", ("台北市", "大同區"): "9", ("台北市", "中山區"): "10",
    ("台北市", "松山區"): "11", ("台北市", "大安區"): "12", ("台北市", "萬華區"): "13",
    ("台北市", "信義區"): "14", ("台北市", "士林區"): "15", ("台北市", "北投區"): "16",
    ("台北市", "內湖區"): "17", ("台北市", "南港區"): "18", ("台北市", "文山區"): "19",
    ("新北市", "板橋區"): "22", ("新北市", "汐止區"): "23", ("新北市", "新店區"): "30",
    ("新北市", "永和區"): "33", ("新北市", "中和區"): "34", ("新北市", "土城區"): "35",
    ("新北市", "三峽區"): "36", ("新北市", "樹林區"): "37", ("新北市", "鶯歌區"): "38",
    ("新北市", "三重區"): "39", ("新北市", "新莊區"): "40", ("新北市", "泰山區"): "41",
    ("新北市", "林口區"): "42", ("新北市", "蘆洲區"): "43", ("新北市", "五股區"): "44",
    ("桃園市", "中壢區"): "49", ("桃園市", "平鎮區"): "50", ("桃園市", "桃園區"): "55",
    ("桃園市", "龜山區"): "56", ("桃園市", "八德區"): "57", ("桃園市", "蘆竹區"): "61",
    ("新竹市", "東區"): "62", ("新竹市", "北區"): "63", ("新竹市", "香山區"): "64",
    ("新竹縣", "竹北市"): "65", ("新竹縣", "新豐鄉"): "67", ("新竹縣", "寶山鄉"): "71",
    ("新竹縣", "竹東鎮"): "72",
    ("苗栗縣", "竹南鎮"): "78", ("苗栗縣", "頭份市"): "79",
    ("台中市", "中區"): "96", ("台中市", "東區"): "97", ("台中市", "南區"): "98",
    ("台中市", "西區"): "99", ("台中市", "北區"): "100", ("台中市", "北屯區"): "101",
    ("台中市", "西屯區"): "102", ("台中市", "南屯區"): "103", ("台中市", "太平區"): "104",
    ("台中市", "大里區"): "105", ("台中市", "烏日區"): "107", ("台中市", "潭子區"): "114",
    ("台中市", "大雅區"): "115",
    ("台南市", "中西區"): "204", ("台南市", "東區"): "205", ("台南市", "南區"): "206",
    ("台南市", "北區"): "207", ("台南市", "安平區"): "208", ("台南市", "安南區"): "209",
    ("台南市", "永康區"): "210",
    ("高雄市", "新興區"): "241", ("高雄市", "前金區"): "242", ("高雄市", "苓雅區"): "243",
    ("高雄市", "鹽埕區"): "244", ("高雄市", "鼓山區"): "245", ("高雄市", "前鎮區"): "247",
    ("高雄市", "三民區"): "248", ("高雄市", "楠梓區"): "249", ("高雄市", "小港區"): "250",
    ("高雄市", "左營區"): "251", ("高雄市", "岡山區"): "254", ("高雄市", "橋頭區"): "259",
    ("高雄市", "梓官區"): "260", ("高雄市", "彌陀區"): "261", ("高雄市", "鳳山區"): "264",
}
COUNTRY_ID_BY_CITY_AREA.update({
    (city.replace("台", "臺"), area): country_id
    for (city, area), country_id in list(COUNTRY_ID_BY_CITY_AREA.items())
    if "台" in city
})


def _split_booking_address(address):
    address = _fix_address_district_order(str(address or "").strip(), fallback_district="")
    result = {"city": "", "district": "", "country_id": "", "detail": address, "full": address}
    city_m = re.search(r"(?P<city>[^市縣區鄉鎮]{1,6}[市縣])", address)
    if not city_m:
        return result
    city = city_m.group("city")
    after_city = address[city_m.end():]
    city_for_country = _normalize_city_for_country_id(city)
    district_m = re.match(r"(?P<district>[^區鄉鎮市]{1,6}[區鄉鎮])", after_city)
    if not district_m:
        return {
            "city": city_for_country,
            "district": "",
            "country_id": "",
            "detail": after_city.strip() or address,
            "full": f"{city_for_country}{after_city}".strip(),
        }
    district = district_m.group("district")
    detail = after_city[district_m.end():].strip()
    country_id = COUNTRY_ID_BY_CITY_AREA.get((city, district), "") or COUNTRY_ID_BY_CITY_AREA.get((city_for_country, district), "")
    return {
        "city": city_for_country,
        "district": district,
        "country_id": country_id,
        "detail": detail or address,
        "full": f"{city_for_country}{district}{detail}".strip(),
    }


def _assert_address_region_resolved(address_parts, original_address, context="地址"):
    if address_parts.get("city") and address_parts.get("district") and not address_parts.get("country_id"):
        raise Exception(
            f"{context}無法對應後台縣市/區域下拉選單：{original_address}。"
            "已停止成單，不會自動改成大安區；請確認此區域是否在服務範圍或補上區域對照。"
        )


def _area_district_from_info(area_info):
    text = str(
        (area_info or {}).get("area_name")
        or (area_info or {}).get("name")
        or (area_info or {}).get("area")
        or (area_info or {}).get("district")
        or ""
    ).strip()
    m = re.search(r"([^區鄉鎮市]{1,6}[區鄉鎮])", text)
    return m.group(1) if m else ""


def _complete_missing_district(address_parts, area_info, original_address, context="地址"):
    if address_parts.get("district"):
        return address_parts
    city = address_parts.get("city", "")
    district = _area_district_from_info(area_info)
    if not city or not district:
        raise Exception(f"{context}「{original_address}」無法判斷區域，已停止成單，請確認地址是否正確。")
    country_id = COUNTRY_ID_BY_CITY_AREA.get((city, district), "")
    if not country_id:
        raise Exception(f"{context}「{original_address}」找到區域「{district}」，但無法對應後台下拉選單，已停止成單。")
    detail = address_parts.get("detail", "")
    return {"city": city, "district": district, "country_id": country_id, "detail": detail, "full": f"{city}{district}{detail}".strip()}


def _validate_area_not_known_bad(address, area_info, context=""):
    area_id = str((area_info or {}).get("area_id") or (area_info or {}).get("areaId") or "").strip()
    if area_id != "25":
        return
    district = _extract_district_from_address(address)
    if district and district != "大安區":
        prefix = f"{context}：" if context else ""
        raise Exception(
            f"{prefix}查詢地址區域疑似錯誤：地址寫的是「{district}」，"
            "但後台回傳 area_id=25（大安區）。已停止成單，避免地址被加成台北市大安區。"
        )


def _validate_address_before_submit(address, area_id, context=""):
    if re.search(r"[^市縣區鄉鎮]{1,6}[市縣].+[^市縣區鄉鎮]{1,6}[市縣]", str(address or "")):
        prefix = f"{context}：" if context else ""
        raise Exception(
            f"{prefix}送出前地址格式異常：地址內出現兩個縣市「{address}」。"
            "已停止成單，避免沿用後台錯誤加上的市/區前綴。"
        )
    if str(area_id or "").strip() == "25":
        _validate_area_not_known_bad(address, {"area_id": "25"}, context=context)
    fixed = _fix_address_district_order(address, fallback_district="")
    if normalize_addr_for_match(fixed) != normalize_addr_for_match(address):
        prefix = f"{context}：" if context else ""
        raise Exception(
            f"{prefix}送出前地址格式異常：目前地址是「{address}」，"
            f"整理後會變成「{fixed}」。已停止成單，請確認不要沿用後台錯誤地址。"
        )
