#!/usr/bin/env python3
"""ユーザー名とメッセージから「キャラクターが吹き出しで喋る」画像を作り、LX-D02 で印刷する。

  ./chatprint.py -u なお -m "こんにちは！"
  ./chatprint.py -m "名前なし"            # ユーザー名は「ナナシさん」
  echo "長いメッセージ" | ./chatprint.py -u なお
  ./chatprint.py                         # 対話モード（繰り返し入力）
  ./chatprint.py -u なお -m "test" --preview out.png --no-print
  ./chatprint.py -c kuro -m "にゃー"       # キャラクター指定（省略時はランダム）
  ./chatprint.py --list                  # キャラクター一覧
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

import characters
import lxd02
import render

DEFAULT_USER = "ナナシさん"


def build_image(args, username: str, message: str):
    message = message.replace("\\n", "\n")
    key = resolve_character(args.character)
    if key is None and args.character:
        img = render.render(username, message, character=render.load_character(args.character),
                            font_size=args.font_size)
    else:
        character, mouth_y = characters.get(key)
        img = render.render(username, message, character=character, mouth_y=mouth_y,
                            font_size=args.font_size)
    return render.add_feed(img, args.feed)


def resolve_character(spec: str | None) -> str | None:
    """Built-in key from a key or display name; None for random or an image path."""
    if not spec:
        return None
    for key, (label, _, _) in characters.CHARACTERS.items():
        if spec in (key, label) or label.startswith(spec):
            return key
    if os.path.isfile(spec):
        return None
    raise SystemExit(f"キャラクター「{spec}」がありません。--list で一覧を表示できます")


def list_characters():
    for key, (label, _, _) in characters.CHARACTERS.items():
        print(f"  {key:<10} {label}")


def output(args, username: str, message: str):
    img = build_image(args, username, message)
    if args.preview:
        img.save(args.preview)
        print(f"プレビューを保存しました: {args.preview}")
    if not args.no_print:
        asyncio.run(lxd02.print_image(img, density=args.density, address=args.address))


def interactive(args):
    print("対話モード: ユーザー名とメッセージを入力すると印刷します（Ctrl+D / Ctrl+C で終了）")
    username = args.user or DEFAULT_USER
    while True:
        try:
            username = input(f"ユーザー名 [{username}]: ").strip() or username
            message = input("メッセージ: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not message:
            continue
        try:
            output(args, username, message)
        except lxd02.PrinterError as e:
            print(f"エラー: {e}", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description="キャラクターの吹き出しメッセージを LX-D02 で印刷します")
    p.add_argument("-u", "--user", help=f"ユーザー名（省略時は「{DEFAULT_USER}」）")
    p.add_argument("-m", "--message", help="メッセージ（省略時は標準入力、端末なら対話モード）")
    p.add_argument("-d", "--density", type=int, default=3, choices=range(1, 8), metavar="1-7",
                   help="印刷濃度 1〜7（既定 3）")
    p.add_argument("--feed", type=int, default=40, help="印刷後の空白行数（既定 40）")
    p.add_argument("--font-size", type=int, default=24, help="メッセージの文字サイズ（既定 24）")
    p.add_argument("-c", "--character",
                   help="キャラクター名（--list 参照）または画像のパス。省略時はランダム")
    p.add_argument("-l", "--list", action="store_true", help="キャラクター一覧を表示")
    p.add_argument("-a", "--address", help="プリンタのアドレス/UUID（省略時は名前が LX で始まる機器を自動検出）")
    p.add_argument("-p", "--preview", help="生成画像を PNG で保存する")
    p.add_argument("-n", "--no-print", action="store_true", help="印刷しない（プレビューのみ）")
    args = p.parse_args()

    if args.list:
        list_characters()
        return
    resolve_character(args.character)  # fail fast on an unknown name

    message = args.message
    if message is None:
        if sys.stdin.isatty():
            interactive(args)
            return
        message = sys.stdin.read().strip()

    try:
        output(args, args.user or DEFAULT_USER, message)
    except lxd02.PrinterError as e:
        sys.exit(f"エラー: {e}")


if __name__ == "__main__":
    main()
