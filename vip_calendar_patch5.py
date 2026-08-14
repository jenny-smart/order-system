# -*- coding: utf-8 -*-
"""Small UI alignment patch for VIP order/calendar sync.

Keeps the left order selector and right calendar selector at the same vertical
level by removing the extra order caption row. This makes service date align
with calendar date, and service period align with calendar period.
"""


def apply_patch(vcs, vcp):
    import vip_calendar_patch4 as patch4

    def _select_order(st, vcs_module, orders_list, key="vipcal_order"):
        if not orders_list:
            st.warning("此範圍沒有後台訂單可作為來源")
            return None
        labels = [vcs_module._order_label(o) for o in orders_list]
        chosen = st.selectbox("選擇後台訂單／範本", labels, key=key)
        return orders_list[labels.index(chosen)]

    patch4._select_order = _select_order
    return vcs
