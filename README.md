# 4行日記 (QuadDiary)

毎日決まった時刻にポップアップで「4行日記」の入力を促す、Windows のシステムトレイ
常駐アプリです。入力した日記は本機（ローカル）に保存し、任意で Confluence にも同期できます。
Python + PySide6 製。

「4行日記」は次の4項目を書きます。

| 項目 | 内容 |
|------|------|
| 事実 | 今日実際に起きたこと |
| 発見 | 今日気づいたこと・注目したこと |
| 教訓 | 今日得た教訓 |
| 宣言 | 明日からの行動宣言 |

---

# インストール（exe で使う場合）

1. [Releases](https://github.com/T-King-Sawada/quad-diary/releases/latest) から `QuadDiary-Setup.exe` をダウンロードして実行
2. 「Windows によって PC が保護されました」と出たら **「詳細情報」→「実行」**
   （コード署名をしていないため表示されます。ダウンロード元が上記 Releases であることを確認してください）
3. インストール後、スタートメニューの「QuadDiary」から起動 → 初回設定ウィザード（[4.](#4-初回設定ウィザード)）

- 管理者権限は不要です（`%LOCALAPPDATA%\Programs\QuadDiary` にインストール）。
- 新しいバージョンはアプリが起動時に確認し、確認ダイアログの後に自動で更新します。
- Python から動かす場合は以下の「使用説明」を参照してください。

---

# 使用説明

## 1. 動作環境

- Windows 10 / 11
- Python 3.10 以上（このリポジトリは 3.12 で動作確認）
- 依存パッケージ：`PySide6` / `requests` / `keyring`（`requirements.txt`）

## 2. セットアップ（初回のみ）

仮想環境を作り、依存パッケージを入れます。

```bat
python -m venv "%USERPROFILE%\ddvenv"
"%USERPROFILE%\ddvenv\Scripts\python.exe" -m pip install -r requirements.txt
```

> なぜホーム直下(`%USERPROFILE%\ddvenv`)か：プロジェクトが OneDrive 配下の長いパスにあると、
> PySide6 のインストールで Windows のパス長制限(260文字)を超えてエラー(WinError 206)になるため、
> 短いパスに venv を作って回避しています。

## 3. 起動方法

| 方法 | 用途 |
|------|------|
| `run.bat` をダブルクリック | 通常起動（コンソール無しで常駐）|
| `run_debug.bat` をダブルクリック | デバッグ起動（コンソールにログ表示）|

どちらも `%USERPROFILE%\ddvenv` の Python を使います。起動すると日記ウィンドウが開き、
同時にタスクトレイに常駐します。

> **タスクトレイのアイコンが見えないとき**：Windows 11 は新しいトレイアイコンを
> タスクバー右の「∧（隠れているインジケーター）」に隠します。クリックして出てくる
> 青いアイコンを、タスクバーへドラッグすれば常に表示されます。

## 4. 初回設定ウィザード

`config.json` が無い初回起動時、設定ウィザードが開きます。

- **リマインダー時刻**：毎日この時刻に入力を促します（例 18:30）
- **Windows ログオン時に自動起動**：ON にすると PC ログオン時に常駐開始
- **Confluence 同期（任意）**：使う場合はチェックし、認証情報等を入力（→ 6章）

「あとで」を押せばスキップできます（後から「設定」で変更可能）。

## 5. 日常の使い方

タスクトレイのアイコンを**右クリック**するとメニューが出ます。

| メニュー | 動作 |
|----------|------|
| **今日を書く** | 4行日記の入力画面を開く（保存済みなら内容が入った状態で開く）|
| **設定** | リマインダー時刻・ポップアップ強度・Confluence などを設定 |
| **同期する** | 未同期（pending/failed）の日記を同期先へ再送 |
| **更新を確認** | 最新版があれば確認のうえ自動更新 |
| **終了** | アプリを終了 |

起動時にも自動で更新を確認し、新しい版があれば「更新しますか？」と尋ねます
（設定・日記データ・保存済みトークンは保持されます）。

- 設定時刻になると、その日まだ未入力なら入力画面が自動で開きます。
- 入力画面は常に最前面に表示されます。
- **保存**で本機に保存（Confluence 有効時は続けて同期）。
- **N分後に再通知**（スヌーズ）：あとで書きたいとき。1日の回数上限あり（設定可能）。
- 同じ日に再度開くと、保存済みの内容を**編集して上書き**できます。

### 4行に収まらない日（追記）

入力画面の下にある `＋ 思考` `＋ タネ` を押すと、任意の追記欄が増えます。

| ボタン | 用途 |
|---|---|
| `＋ 思考` | 4行に収まらない考え |
| `＋ タネ` | 「後で書きたい」だけのメモ。書けない日の逃げ道 |

- 押すまで入力欄は出ません（空欄を見て「埋めなきゃ」と思わないように）
- 何件でも追加できます。`×` で消せます
- 空のまま保存すると、その追記は記録されません
- 4行が空でも、追記だけ書いた日は保存できます
- 追記に検証は付きません（宣言と違って、後から浮き上がってくることはありません）

### リマインダーが出る条件

設定した時刻（既定 18:30）になると、**その日に何を書いていても1回は窓が出ます**。

- 昼のうちに手動で書いて保存しても、18:30 に「追記しますか？」と出ます（その日の残りを書き足せます）
- 手動で開いてキャンセルしても、18:30 の窓には影響しません
- 18:30 の窓で保存するか「追記しない」を選ぶと、その日はもう出ません（アプリを再起動しても出ません）
- 18:30 の窓をキャンセルした場合だけは、アプリを再起動するともう一度出ます（書き忘れ防止のため）

### ポップアップ強度（popup_mode）

| モード | 動作 |
|--------|------|
| `normal` | 通常の窓。×やキャンセルでそのまま閉じられる |
| `force` | 未保存で閉じようとすると確認し、再通知へ誘導する |

どちらのモードでも、保存に必要なのは **1項目だけ**です。書けない日に1行で終われることが、続けられることの前提なので、force でも4項目すべては要求しません。

## 6. Confluence 同期の設定

日記ページを Confluence に1日1ページずつ作成（既存なら更新）できます。
（Confluence は連携先の一例です。将来的に Notion / Google Docs などへの対応も検討しています。）

### 6-1. API Token を発行

https://id.atlassian.com/manage-profile/security/api-tokens で発行します。
**スコープ付きトークン**の場合は次の3つを付与してください。

```
write:page:confluence
read:page:confluence
read:space:confluence
```

### 6-2. 設定画面の入力項目

| 項目 | 説明 |
|------|------|
| Base URL | `https://<組織>.atlassian.net/wiki`（末尾の `/wiki` まで含める）|
| Space ID | **数値のID**（スペースのキーではない）|
| Parent Page ID | 日記を置くページのID（URL `/pages/123456/...` の数字部分）|
| Email | Atlassian アカウントのメール |
| API Token | 6-1 で発行したトークン（資格情報マネージャーに保存される）|
| 年→月の親ページを自動作成 | ON で `Parent` の下に `YYYY` → `YYYY-MM` を自動作成し、その下に日記を置く |

> **Space ID（数値）の調べ方**：ログイン状態で
> `https://<組織>.atlassian.net/wiki/api/v2/spaces?type=personal` を開くと、
> 各スペースの数値 `id` が分かります（個人スペースの場合）。

入力後、**「接続テスト」**で「接続成功（Space: …）」が出れば OK。「保存」で確定します。

### 6-3. 同期の挙動

```
日記を保存 → まず本機(JSONL)に保存 → Confluence 有効なら別スレッドで同期
  成功 → sync_status = synced（同名ページがあれば内容を更新）
  失敗 → sync_status = failed（本機データは保持。トレイ「同期する」で再送可能）
```

- 同期失敗しても**本機の日記は失われません**。
- 同名タイトルのページが既にあれば**更新**します（重複作成エラーを回避）。
- アクセス制御（誰がどこに書けるか）は **Confluence 側のスペース/ページ権限**で管理してください。

## 7. データの保存場所

ユーザーデータは散らからないよう **1 フォルダに集約**されます。

```
%APPDATA%\QuadDiary\        ← exe 実行時（どこに exe を置いても固定）
├─ config.json              個人設定（差分のみ・非秘密）
├─ data/                    日記本体（diary_YYYY.jsonl）
└─ logs/                    app.log
```

- exe をどこに置いても・移動・更新・再ビルドしても、データはこの 1 フォルダのまま。
- 旧バージョン（exe の隣にデータを作る方式）からは、**初回起動時に自動移行**します。
- 管理者デフォルト `config.default.json` は **exe と同じフォルダ**に置きます（配布物に同梱）。
- 開発（`run.bat` のスクリプト実行）時は、従来どおりプロジェクト直下に保存します。

API Token は Windows **資格情報マネージャー**（エントリ名 `DailyDiary` ※内部IDのため旧名を維持）
に保存され、ファイルには平文で残しません。

## 8. 設定の優先順位（2層構成）

後のものほど優先（上書き）。

1. コード内の既定値
2. `config.default.json` … 管理者デフォルト（配布時に接続先を事前設定）
3. `config.json` … 個人の上書き（差分のみ自動保存）
4. **API Token** … Windows 資格情報マネージャー

`config.default.json` で接続先を用意して配布すれば、利用者は初回ウィザードで
**Parent Page ID・Email・API Token を入力するだけ**で使えます。

## 9. トラブルシューティング

| 症状 | 対処 |
|------|------|
| コードを変えたのに反映されない | トレイ「終了」で**完全終了**してから起動し直す（常駐中は古いコードのまま）|
| トレイアイコンが見えない | タスクバー右の「∧」を確認し、アイコンをタスクバーへドラッグ |
| 同期が HTTP 401 | Email/Token を確認。スコープ付きトークンは内部で `api.atlassian.com` 経由で認証 |
| 同期が HTTP 403 | スコープ不足（write:page / read:page / read:space）またはページ権限不足 |
| 同期が「同期失敗」 | 本機には保存済み。原因を直して「同期する」で再送 |
| 詳細を調べたい | `logs/app.log` を確認、または `run_debug.bat` でコンソール起動 |
| 旧 `QuadDiary.exe`（単体版）が「Could not create temporary directory」で起動しない | 単体版は `%TEMP%` への展開が必要なため環境によって失敗します。`QuadDiary-Setup.exe` でインストールし直してください（データは `%APPDATA%\QuadDiary` にあるのでそのまま引き継がれます）|
| ログオン時に自動起動しない | 設定で「自動起動」を ON にしてアプリを一度起動すると、登録先が今の exe に書き直されます |

---

# 開発者向け

## モジュール構成

```
4行日記/
├─ main.py                  起動・全体制御（AppController）
├─ app/
│  ├─ tray.py               システムトレイ常駐・メニュー
│  ├─ reminder.py           定時監視・スヌーズ・1日1回制御
│  ├─ diary_dialog.py       4行入力ウィンドウ（再利用・非モーダル）
│  ├─ settings_dialog.py    設定画面（接続テスト付き）
│  ├─ first_run.py          初回設定ウィザード
│  ├─ storage.py            JSONL 保存（年別・同日 upsert）
│  ├─ providers/            同期先プロバイダの共通IF（base.py）とレジストリ
│  ├─ confluence_client.py  Confluence プロバイダ（v2 API・gateway 経由・upsert・月次親）
│  ├─ sync_worker.py        同期をバックグラウンドスレッドで実行（プロバイダ非依存）
│  ├─ updater.py            GitHub リリースからの自動更新
│  ├─ secrets_store.py      API Token を資格情報マネージャーへ（keyring）
│  ├─ config.py             2層設定の読み書き（差分保存・トークン注入）
│  ├─ single_instance.py    多重起動防止（QLocalServer）
│  ├─ autostart.py          ログオン自動起動（レジストリ）
│  ├─ icon.py               トレイアイコン描画
│  ├─ paths.py              Portable パス解決
│  └─ logger.py             ログ（logs/app.log）
├─ installer.iss            Inno Setup スクリプト（QuadDiary-Setup.exe）
├─ data/  logs/  config*.json  requirements.txt  run*.bat  build.bat
```

## テスト

ロジック（reminder / config / storage / confluence_client）の自動テストがあります。

```bat
pip install -r requirements-dev.txt   :: 初回のみ
"%USERPROFILE%\ddvenv\Scripts\python.exe" -m pytest
```

GUI（トレイ・ウィンドウ）は自動テスト対象外のため、手動確認で補完します。

## 同期先プロバイダの追加

連携先は `app/providers/base.py` の `SyncProvider` インターフェイス
（`test_connection` / `upsert_entry`）で抽象化されています。Notion / Google Docs
などを追加する場合は、`SyncProvider` を実装したクラスを作り、
`app/providers/__init__.py` の `_provider_classes()` に登録すれば、同期処理は
そのまま新プロバイダにも適用されます（設定UIは各プロバイダ用に追加）。

## コード変更後の再起動ルール

多重起動防止により、`run.bat` を再実行しても新コードは読み込まれません。
**必ずトレイ「終了」で完全終了してから起動し直してください。**

## ビルド（配布用インストーラ）

```bat
pip install -r requirements-dev.txt   :: 初回のみ（pyinstaller 含む）
build.bat                             :: dist\QuadDiary-Setup.exe を生成
```

前提：[Inno Setup 6](https://jrsoftware.org/isinfo.php) をインストールしておくこと。

`build.bat` は次の 2 段階です。

1. PyInstaller `--noconsole --onedir` → `dist\QuadDiary\`（`QuadDiary.exe` + `_internal\`）。
   keyring の Windows バックエンドを hidden-import で同梱。
2. Inno Setup（`installer.iss`）→ `dist\QuadDiary-Setup.exe`。バージョンは `app/__init__.py` の `__version__`。

> **なぜ onefile をやめたか**：onefile の exe は起動のたびに `%TEMP%` へ自己展開します。
> セキュリティソフトや TEMP フォルダの権限・会社PCのポリシー次第で
> 「Could not create temporary directory」となり起動できない環境があるため、
> 展開不要の onedir をインストーラで配る方式にしました。

### 配布方法（GitHub Releases）

1. `app/__init__.py` の `__version__` を上げて `build.bat`
2. タグ `vX.Y.Z` でリリースを作り、**`dist\QuadDiary-Setup.exe` をアセットとして添付**
   （アプリの自動更新はこのファイル名を探します）

インストーラの挙動：

- インストール先：`%LOCALAPPDATA%\Programs\QuadDiary`（ユーザー単位・管理者権限不要）
- スタートメニューにショートカット（任意でデスクトップにも）
- 自動更新時はサイレントで上書きインストールし、アプリを再起動
- アンインストール：Windows の「設定 → アプリ」から。ログオン自動起動の登録も削除。
  日記データ・設定（`%APPDATA%\QuadDiary`）は残します。
- `QuadDiary-Setup.exe` と同じフォルダに `config.default.json` を置いてから実行すると、
  インストール先へコピーされます（管理者が接続先を事前設定する場合）。

利用者は `QuadDiary-Setup.exe` を実行 → 初回ウィザードで Email / API Token / Parent Page ID を入力。

> **旧 onefile 版（v1.6.0 以前）の利用者**：アプリ内の自動更新は `QuadDiary.exe` という
> アセットしか探さないため、Setup だけのリリースは検出されません。
> `QuadDiary-Setup.exe` を手動で一度実行してもらえば、以降はインストール版として自動更新されます
> （自動起動の登録先も初回起動時に新しい exe へ自動で書き換わります）。

## 開発ステータス

- **Phase 1（完了）**：トレイ常駐 / 定時リマインダー / 4行入力 / JSONL保存 / 設定 / 自動起動
- **Phase 2（完了）**：Force モード・スヌーズ・ログ・常時最前面・多重起動防止
- **Phase 3（完了）**：Confluence 同期（接続テスト・作成/更新 upsert・失敗リトライ・月次親ページ自動作成）
- **Phase 4（完了）**：設定2層化・初回ウィザード・Credential Manager・PyInstaller .exe 化

## ライセンス

[MIT License](LICENSE) で公開しています。自由に利用・改変・再配布できます。

### サードパーティ

- [PySide6 (Qt for Python)](https://www.qt.io/qt-for-python) — **LGPLv3**。本アプリは PySide6 を利用しています。
  配布する `.exe` には Qt のライブラリが同梱されます。LGPL の条件（ライブラリ差し替えの自由など）に従ってください。
- [requests](https://requests.readthedocs.io/) — Apache-2.0
- [keyring](https://github.com/jaraco/keyring) — MIT
