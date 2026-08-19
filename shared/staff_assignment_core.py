# ============================================================
# 檔名：shared/staff_assignment_core.py
# 功能：檸檬保留單換正式專員的共用配班核心；先硬性排除，再依交通與適配條件排序專員組合。
# 更新時間：2026-08-19
# ============================================================
# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


@dataclass
class AssignmentContext:
    order_no: str
    service_date: str
    period: str
    address: str
    people_needed: int = 2
    is_vip: bool = False
    is_returning_customer: bool = False
    gender_requirement: str = ""
    height_requirement: str = ""
    body_requirement: str = ""
    preferred_staff_ids: Set[str] = field(default_factory=set)
    visited_staff_ids: Set[str] = field(default_factory=set)
    complained_staff_ids: Set[str] = field(default_factory=set)
    customer_tags: Set[str] = field(default_factory=set)
    required_skills: Set[str] = field(default_factory=set)
    case_tags: Set[str] = field(default_factory=set)


@dataclass
class StaffCandidate:
    staff_id: str
    name: str
    rating: float = 0.0
    gender: str = ""
    height_cm: Optional[float] = None
    body_tags: Set[str] = field(default_factory=set)
    skills: Set[str] = field(default_factory=set)
    customer_fit_tags: Set[str] = field(default_factory=set)
    case_fit_tags: Set[str] = field(default_factory=set)
    unavailable_case_tags: Set[str] = field(default_factory=set)
    incompatible_staff_ids: Set[str] = field(default_factory=set)
    similarity_tags: Set[str] = field(default_factory=set)
    observation: bool = False
    intern: bool = False
    machine_required: bool = False
    home_to_case_minutes: Optional[int] = None
    previous_case_to_case_minutes: Optional[int] = None
    case_to_home_minutes: Optional[int] = None
    available: bool = True
    availability_reason: str = ""


@dataclass
class CombinationResult:
    staff: Tuple[StaffCandidate, ...]
    eligible: bool
    score: float
    hard_failures: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def names(self) -> str:
        return "＋".join(s.name for s in self.staff)


def _norm(value: str) -> str:
    return str(value or "").strip().lower()


def _hard_failures_for_staff(ctx: AssignmentContext, staff: StaffCandidate) -> List[str]:
    failures: List[str] = []
    if not staff.available:
        failures.append(staff.availability_reason or "該時段不可排")
    if staff.staff_id in ctx.complained_staff_ids:
        failures.append("曾被此客戶客訴")
    if ctx.gender_requirement and _norm(staff.gender) != _norm(ctx.gender_requirement):
        failures.append("不符合性別限制")
    if ctx.height_requirement:
        req = _norm(ctx.height_requirement)
        if req.startswith(">="):
            try:
                if staff.height_cm is None or staff.height_cm < float(req[2:]):
                    failures.append("不符合身高限制")
            except ValueError:
                pass
    if ctx.body_requirement and _norm(ctx.body_requirement) not in {_norm(x) for x in staff.body_tags}:
        failures.append("不符合體型限制")
    if ctx.required_skills and not ctx.required_skills.issubset(staff.skills):
        failures.append("缺少必要特殊清潔能力")
    if ctx.case_tags & staff.unavailable_case_tags:
        failures.append("屬於專員不擅長／禁止案場")
    # 三段交通資料只要明確標成負值，就視為不可達；真正分鐘上限由上層資料源決定。
    for label, minutes in (
        ("家到案場", staff.home_to_case_minutes),
        ("上一案場到本案場", staff.previous_case_to_case_minutes),
        ("案場到家", staff.case_to_home_minutes),
    ):
        if minutes is not None and minutes < 0:
            failures.append(f"{label}不可達")
    return failures


def _pair_failures(staff: Sequence[StaffCandidate]) -> List[str]:
    failures: List[str] = []
    for a, b in combinations(staff, 2):
        if b.staff_id in a.incompatible_staff_ids or a.staff_id in b.incompatible_staff_ids:
            failures.append(f"{a.name}／{b.name}不可搭配")
    if staff:
        avg_rating = sum(float(x.rating or 0) for x in staff) / len(staff)
        if avg_rating < 4.0:
            failures.append(f"夥伴星等組合低於4分（{avg_rating:.2f}）")
    return failures


def _soft_score(ctx: AssignmentContext, staff: Sequence[StaffCandidate]) -> Tuple[float, List[str]]:
    score = 0.0
    reasons: List[str] = []
    ids = {x.staff_id for x in staff}

    # 交通優先：三段越短越好；沒有資料不加不扣。
    travel_total = 0
    travel_count = 0
    for s in staff:
        for minutes in (s.home_to_case_minutes, s.previous_case_to_case_minutes, s.case_to_home_minutes):
            if minutes is not None and minutes >= 0:
                travel_total += minutes
                travel_count += 1
    if travel_count:
        score += max(0.0, 120.0 - travel_total / max(1, len(staff)))
        reasons.append(f"交通總負擔 {travel_total} 分鐘")

    visited = ids & ctx.visited_staff_ids
    if ctx.is_vip:
        if visited:
            score += 80
            reasons.append("VIP 至少一位曾服務")
        else:
            score -= 120
            reasons.append("VIP 無曾服務專員")
    elif ctx.is_returning_customer and visited:
        score += 45
        reasons.append("舊客有曾服務專員")

    preferred = ids & ctx.preferred_staff_ids
    if preferred:
        score += 55 * len(preferred)
        reasons.append("包含喜愛專員")

    fit_count = sum(len(ctx.customer_tags & s.customer_fit_tags) for s in staff)
    if fit_count:
        score += 15 * fit_count
        reasons.append("符合客戶互動／個性需求")

    case_fit = sum(len(ctx.case_tags & s.case_fit_tags) for s in staff)
    if case_fit:
        score += 15 * case_fit
        reasons.append("符合案場類型")

    skill_hits = sum(len(ctx.required_skills & s.skills) for s in staff)
    if skill_hits:
        score += 20 * skill_hits
        reasons.append("符合特殊清潔能力")

    machine_count = sum(1 for s in staff if s.machine_required)
    if machine_count:
        score -= 8 * machine_count
        reasons.append("含機器調度成本")

    # 避免同性質夥伴全部疊在一起；有互補標籤者較佳。
    if len(staff) > 1:
        common = set(staff[0].similarity_tags)
        for s in staff[1:]:
            common &= s.similarity_tags
        if common:
            score -= 12
            reasons.append("夥伴性質較相近")
        else:
            score += 10
            reasons.append("夥伴組合較互補")

    # 觀察名單／實習不是直接禁止，而是降低排序，交由上層搭配成熟夥伴。
    if any(s.observation for s in staff):
        score -= 10
        reasons.append("含觀察名單專員")
    if any(s.intern for s in staff):
        score -= 12
        reasons.append("含實習專員")

    score += sum(float(s.rating or 0) for s in staff) * 3
    return score, reasons


def evaluate_combination(ctx: AssignmentContext, staff: Sequence[StaffCandidate]) -> CombinationResult:
    if len(staff) != int(ctx.people_needed or 0):
        return CombinationResult(tuple(staff), False, -999999, ["專員人數不符"])
    if len({s.staff_id for s in staff}) != len(staff):
        return CombinationResult(tuple(staff), False, -999999, ["同一位專員不可重複安排"])

    failures: List[str] = []
    for s in staff:
        failures.extend(f"{s.name}：{x}" for x in _hard_failures_for_staff(ctx, s))
    failures.extend(_pair_failures(staff))
    if failures:
        return CombinationResult(tuple(staff), False, -999999, failures)

    score, reasons = _soft_score(ctx, staff)
    return CombinationResult(tuple(staff), True, score, [], reasons)


def rank_combinations(ctx: AssignmentContext, candidates: Iterable[StaffCandidate], limit: int = 20) -> List[CombinationResult]:
    pool = list(candidates or [])
    results = [evaluate_combination(ctx, combo) for combo in combinations(pool, int(ctx.people_needed or 0))]
    eligible = [r for r in results if r.eligible]
    eligible.sort(key=lambda r: (-r.score, r.names))
    return eligible[: max(1, int(limit or 20))]
