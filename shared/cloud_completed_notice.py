"""GitHub Actions 雲端執行：已成單通知分批產生、寫回與續跑。"""
from __future__ import annotations

import argparse

import orders
from accounts import ACCOUNTS
from shared import notification_service
from shared.line_notice_sheet import (
    filter_completed_address_groups, filter_groups_by_calendar, groups_from_dataframe,
    write_results_to_source,
)


def _key(group):
    return (str(group.get("name") or "").strip(), "".join(str(group.get("address") or "").split()))


def run(sheet, rows="", env="prod", batch_size=8):
    worksheet, df = orders.load_worksheet(sheet)
    groups = groups_from_dataframe(df, rows)
    groups, completed = filter_completed_address_groups(groups, df)
    source = list(groups)
    print(f"START pending_groups={len(groups)} skipped_completed={completed}", flush=True)
    kept, skipped = filter_groups_by_calendar(
        groups, orders, orders.build_gcal_service(), orders.GOOGLE_CALENDAR_MAP, ACCOUNTS,
        progress_callback=lambda checked, total, matched, skipped_count, _entry: print(
            f"CALENDAR {checked}/{total} matched={matched} skipped={skipped_count}", flush=True
        ),
    )
    source_by_key = {_key(group): group for group in source}
    kept_keys = {_key(group) for group in kept}
    skipped_only = [group for group in source if _key(group) not in kept_keys]
    if skipped_only:
        write_results_to_source(worksheet, skipped_only, [], skipped)
    by_region = {}
    for group in kept:
        region = orders.get_region_by_address(group.get("address", ""), ACCOUNTS)
        by_region.setdefault(region, []).append(group)
    done = failed = 0
    for region, region_groups in by_region.items():
        account = ACCOUNTS.get(region) or {}
        email, password = str(account.get("email") or ""), str(account.get("password") or "")
        if not email or not password:
            raise RuntimeError(f"{region or '未知地區'}未設定雲端後台帳密")
        region_groups.sort(key=lambda group: min(int(entry["row"]) for entry in group.get("entries") or [{}]), reverse=True)
        for start in range(0, len(region_groups), max(1, int(batch_size))):
            batch = region_groups[start:start + max(1, int(batch_size))]
            results = notification_service.build_many_combined_line_messages(env, email, password, batch, max_workers=4)
            batch_keys = {_key(group) for group in batch}
            batch_source = [source_by_key[key] for key in batch_keys]
            batch_skipped = [entry for entry in skipped if (str(entry.get("name") or "").strip(), "".join(str(entry.get("address") or "").split())) in batch_keys]
            write_results_to_source(worksheet, batch_source, results, batch_skipped)
            done += len(results); failed += sum(bool(item.get("error")) for item in results)
            print(f"BATCH done={done} failed={failed} remaining={len(kept)-done}", flush=True)
    print(f"FINISH done={done} failed={failed} calendar_skipped={len(skipped)}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--rows", default="")
    parser.add_argument("--env", default="prod")
    parser.add_argument("--batch-size", type=int, default=8)
    args = parser.parse_args()
    run(args.sheet, args.rows, args.env, args.batch_size)


if __name__ == "__main__":
    main()
