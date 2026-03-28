#!/usr/bin/env python3
"""cron式パーサー: 次回実行時刻を計算する

使い方:
    python3 scripts/cron-next.py "*/10 * * * *"
    python3 scripts/cron-next.py "7 8-20 * * 1-5"
    python3 scripts/cron-next.py "0 9 * * 1-5" "2026-03-28 10:00:00"

出力: YYYY-MM-DD HH:MM:00（ローカルタイム）

対応パターン: *, */N, N, N-M, N,M,O, N-M/S
5フィールド: 分 時 日 月 曜日
"""

import sys
from datetime import datetime, timedelta


def parse_field(expr: str, min_val: int, max_val: int) -> set[int]:
    """cron式の1フィールドを解析し、有効な値のセットを返す"""
    result = set()
    for part in expr.split(","):
        part = part.strip()
        if part == "*":
            result.update(range(min_val, max_val + 1))
        elif "/" in part:
            base, step_str = part.split("/", 1)
            step = int(step_str)
            if base == "*":
                start = min_val
                end = max_val
            elif "-" in base:
                start, end = map(int, base.split("-", 1))
            else:
                start = int(base)
                end = max_val
            result.update(range(start, end + 1, step))
        elif "-" in part:
            start, end = map(int, part.split("-", 1))
            result.update(range(start, end + 1))
        else:
            result.add(int(part))
    return result


def next_run(cron_expr: str, after: datetime | None = None) -> datetime | None:
    """cron式から次回実行時刻を計算する

    Args:
        cron_expr: 5フィールドcron式（分 時 日 月 曜日）
        after: この時刻以降の次回を計算（デフォルト: 現在時刻）

    Returns:
        次回実行時刻のdatetime、2年以内に見つからなければNone
    """
    fields = cron_expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"cron式は5フィールド必要です（{len(fields)}フィールド検出）: {cron_expr}")

    minutes = parse_field(fields[0], 0, 59)
    hours = parse_field(fields[1], 0, 23)
    days = parse_field(fields[2], 1, 31)
    months = parse_field(fields[3], 1, 12)
    weekdays = parse_field(fields[4], 0, 6)  # 0=日, 1=月, ..., 6=土

    if after is None:
        after = datetime.now()

    # 次の分から探索開始
    current = after.replace(second=0, microsecond=0) + timedelta(minutes=1)

    # 最大2年間探索（無限ループ防止）
    max_date = after + timedelta(days=730)

    while current <= max_date:
        if (current.month in months
                and current.day in days
                and current.hour in hours
                and current.minute in minutes
                and current.isoweekday() % 7 in weekdays):  # isoweekday: 月=1...日=7 → %7で日=0
            return current

        # 効率的な次候補へスキップ
        if current.month not in months:
            # 次の有効な月の1日00:00に飛ぶ
            next_month = current.month + 1
            next_year = current.year
            while next_month <= 12 and next_month not in months:
                next_month += 1
            if next_month > 12:
                next_year += 1
                next_month = min(months) if months else 1
            current = current.replace(year=next_year, month=next_month, day=1, hour=0, minute=0)
            continue

        if current.day not in days or current.isoweekday() % 7 not in weekdays:
            # 翌日00:00に飛ぶ
            current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            continue

        if current.hour not in hours:
            # 次の有効な時間の00分に飛ぶ
            next_hour = current.hour + 1
            if next_hour > 23:
                current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            else:
                valid_hours = sorted(h for h in hours if h >= next_hour)
                if valid_hours:
                    current = current.replace(hour=valid_hours[0], minute=0)
                else:
                    current = (current + timedelta(days=1)).replace(hour=0, minute=0)
            continue

        # 分が合わない場合: 次の有効な分に飛ぶ
        next_min = current.minute + 1
        if next_min > 59:
            current = current.replace(minute=0) + timedelta(hours=1)
        else:
            valid_mins = sorted(m for m in minutes if m >= next_min)
            if valid_mins:
                current = current.replace(minute=valid_mins[0])
            else:
                current = current.replace(minute=0) + timedelta(hours=1)

    return None


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 cron-next.py '<cron式>' [基準時刻]", file=sys.stderr)
        print("例: python3 cron-next.py '*/10 * * * *'", file=sys.stderr)
        sys.exit(1)

    cron_expr = sys.argv[1]

    after = None
    if len(sys.argv) >= 3:
        after = datetime.strptime(sys.argv[2], "%Y-%m-%d %H:%M:%S")

    try:
        result = next_run(cron_expr, after)
    except ValueError as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    if result is None:
        print("エラー: 2年以内に次回実行時刻が見つかりませんでした", file=sys.stderr)
        sys.exit(1)

    print(result.strftime("%Y-%m-%d %H:%M:%S"))


if __name__ == "__main__":
    main()
