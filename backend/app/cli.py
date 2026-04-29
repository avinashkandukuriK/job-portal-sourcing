"""Tiny operations CLI: list adapters, toggle on/off from the terminal.

Usage:
    python -m app.cli adapters list
    python -m app.cli adapters status indeed_resume
    python -m app.cli adapters disable indeed_resume --reason "rate limit"
    python -m app.cli adapters enable indeed_resume
    python -m app.cli adapters pause craigslist --minutes 60 --reason "captcha hit"
    python -m app.cli adapters resume craigslist
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone

from app.adapters import all_adapter_classes, discover_all, get_adapter_class
from app.adapters.toggle_store import get_toggle_store


def _fmt_row(name: str, tier: str, status: str, reason: str | None) -> str:
    return f"  {name:<25} {tier:<14} {status:<22} {reason or ''}"


async def cmd_list() -> None:
    discover_all()
    print(_fmt_row("NAME", "TIER", "STATUS", "REASON"))
    print(_fmt_row("-" * 24, "-" * 12, "-" * 20, "-" * 40))
    for cls in all_adapter_classes():
        inst = cls()
        try:
            status = (await inst.status()).value
            reason = inst.disabled_reason()
        finally:
            await inst.aclose()
        print(_fmt_row(cls.metadata.name, cls.metadata.tier.value, status, reason))


async def cmd_status(name: str) -> None:
    discover_all()
    cls = get_adapter_class(name)
    inst = cls()
    try:
        status = await inst.status()
        toggle = inst.get_toggle()
    finally:
        await inst.aclose()
    print(f"Name:           {cls.metadata.name}")
    print(f"Display name:   {cls.metadata.display_name}")
    print(f"Tier:           {cls.metadata.tier.value}")
    print(f"Status:         {status.value}")
    print(f"Toggle state:   {toggle.state.value}")
    if toggle.paused_until:
        print(f"Paused until:   {toggle.paused_until.isoformat()}")
    if toggle.reason:
        print(f"Reason:         {toggle.reason}")
    if toggle.consecutive_failures:
        print(f"Failures:       {toggle.consecutive_failures}")


def cmd_enable(name: str, reason: str | None) -> None:
    discover_all()
    get_adapter_class(name)  # validate exists
    t = get_toggle_store().enable(name, reason=reason, set_by="cli")
    print(f"Enabled {name} ({t.state.value})")


def cmd_disable(name: str, reason: str | None) -> None:
    discover_all()
    get_adapter_class(name)
    t = get_toggle_store().disable(name, reason=reason, set_by="cli")
    print(f"Disabled {name} ({t.state.value})  reason={t.reason}")


def cmd_pause(name: str, minutes: int, reason: str | None) -> None:
    discover_all()
    get_adapter_class(name)
    until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    t = get_toggle_store().pause(name, until=until, reason=reason, set_by="cli")
    paused_until = t.paused_until.isoformat() if t.paused_until else "unknown"
    print(f"Paused {name} until {paused_until}")


def cmd_resume(name: str) -> None:
    discover_all()
    get_adapter_class(name)
    t = get_toggle_store().enable(name, reason="resumed via cli", set_by="cli")
    print(f"Resumed {name} ({t.state.value})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sourcing")
    sub = p.add_subparsers(dest="group", required=True)

    a = sub.add_parser("adapters", help="manage source adapters")
    asub = a.add_subparsers(dest="action", required=True)

    asub.add_parser("list", help="list all registered adapters with status")

    sp = asub.add_parser("status", help="show one adapter's full status")
    sp.add_argument("name")

    for verb in ("enable", "disable", "resume"):
        vp = asub.add_parser(verb, help=f"{verb} an adapter")
        vp.add_argument("name")
        if verb != "resume":
            vp.add_argument("--reason", default=None)

    pp = asub.add_parser("pause", help="pause an adapter for N minutes")
    pp.add_argument("name")
    pp.add_argument("--minutes", type=int, default=60)
    pp.add_argument("--reason", default=None)

    args = p.parse_args(argv)

    if args.group != "adapters":
        p.print_help()
        return 2

    if args.action == "list":
        asyncio.run(cmd_list())
    elif args.action == "status":
        asyncio.run(cmd_status(args.name))
    elif args.action == "enable":
        cmd_enable(args.name, args.reason)
    elif args.action == "disable":
        cmd_disable(args.name, args.reason)
    elif args.action == "pause":
        cmd_pause(args.name, args.minutes, args.reason)
    elif args.action == "resume":
        cmd_resume(args.name)
    else:
        p.print_help()
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
