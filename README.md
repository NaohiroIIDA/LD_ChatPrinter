# LD_ChatPrinter

ユーザー名とメッセージから「キャラクターが吹き出しで喋っている」画像を作り、
Bluetooth サーマルプリンタ LX-D02 (FunnyPrint) で印刷する CLI。

プロトコルは [cicloid/printable](https://github.com/cicloid/printable) の
`docs/PROTOCOL.md` を参考に Python で実装しています。

## セットアップ

```sh
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
```

## 使い方

```sh
.venv/bin/python chatprint.py -u なお -m "こんにちは！\n改行もできます"
.venv/bin/python chatprint.py -m "名前を省略すると「ナナシさん」"
echo "標準入力からも" | .venv/bin/python chatprint.py -u なお
.venv/bin/python chatprint.py                 # 対話モード（名前とメッセージを繰り返し入力）
.venv/bin/python chatprint.py -u なお -m "確認" -n -p out.png   # 印刷せずプレビューだけ
```

| オプション | 説明 |
| --- | --- |
| `-u, --user NAME` | ユーザー名（既定「ナナシさん」） |
| `-m, --message TEXT` | メッセージ（`\n` で改行。省略時は標準入力／対話モード） |
| `-d, --density 1-7` | 印刷濃度（既定 3） |
| `-c, --character NAME` | キャラクター（キー・日本語名・画像パス。省略時はランダム） |
| `-l, --list` | キャラクター一覧 |
| `--font-size N` | メッセージ文字サイズ（既定 24） |
| `--feed N` | 印刷後の空白行数（既定 40） |
| `-a, --address ID` | 接続先を指定（既定は名前が `LX` で始まる機器を自動検出） |
| `-p, --preview PATH` | 生成画像を PNG 保存 |
| `-n, --no-print` | 印刷しない |

## キャラクター

| キー | 名前 |
| --- | --- |
| `robo` | ネコロボ |
| `shiro` | 白猫 |
| `kuro` | 黒猫 |
| `mike` | 三毛猫 |
| `kijitora` | キジトラ |
| `hachiware` | ハチワレ |
| `siamese` | シャム猫 |
| `fold` | スコティッシュフォールド |
| `persian` | ペルシャ（長毛） |
| `mainecoon` | メインクーン（長毛） |

`-c kuro`、`-c 黒猫`、`-c 三毛`（前方一致）のどれでも指定できます。

## ウェブアプリ

`web/` はブラウザから Web Bluetooth で直接印刷できる静的ページです（PC / Android の Chrome・Edge。iPhone の Safari は Web Bluetooth 非対応）。

```sh
.venv/bin/python -m http.server 8000 -d web   # http://localhost:8000 を Chrome で開く
```

キャラクターを変更したら `make_web_assets.py` で `web/characters/` を作り直します。
`main` に push すると GitHub Actions で GitHub Pages に公開されます（リポジトリ設定で Pages のソースを「GitHub Actions」にしておく）。

## ファイル

- `lxd02.py` — BLE 通信（hello → CRC16-XMODEM 認証 → 濃度 → ラスタ送信、hold/cooldown/再送要求の処理）
- `characters.py` — 内蔵キャラクターの描画
- `render.py` — 384px 幅・1bit の吹き出し画像生成
- `chatprint.py` — CLI
- `make_web_assets.py` — キャラクター画像をウェブアプリ用に書き出し
- `web/` — ウェブアプリ（`lxd02.js` が Web Bluetooth 版ドライバ、`render.js` が画像生成）
