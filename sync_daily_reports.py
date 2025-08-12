import os
import re
import time
from datetime import datetime, timedelta, timezone

import pytz
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError
from notion_client import Client as NotionClient

# ====== 環境変数 ======
SLACK_BOT_TOKEN  = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")
NOTION_TOKEN     = os.getenv("NOTION_TOKEN")
NOTION_DB_ID     = os.getenv("NOTION_DB_ID")

if not all([SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, NOTION_TOKEN, NOTION_DB_ID]):
    raise RuntimeError("環境変数が足りません。SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, NOTION_TOKEN, NOTION_DB_ID を設定してください。")

# ====== クライアント ======
slack  = WebClient(token=SLACK_BOT_TOKEN)
notion = NotionClient(auth=NOTION_TOKEN)

# ====== 設定 ======
JST = pytz.timezone("Asia/Tokyo")
LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "3"))  # 直近何日分見るか（保険）

# 評価期間の設定
EVALUATION_START_MONTH = 4  # 4月開始
EVALUATION_START_DAY = 1    # 1日開始

# 必要なら Slack名→Notion名の手動マッピング（任意）
NAME_ALIAS_MAP = {
    # "Ayumu Miyamoto": "宮本 渉 / Ayumu Miyamoto",
    # "渉 宮本": "宮本 渉 / Ayumu Miyamoto",
}

# ====== Utils ======
def jst_date_str_from_ts(ts: str) -> str:
    # Slack ts は "1733745342.123456" 形式の文字列
    sec = float(ts.split(".")[0])
    dt_utc = datetime.fromtimestamp(sec, tz=timezone.utc)
    dt_jst = dt_utc.astimezone(JST)
    return dt_jst.strftime("%Y-%m-%d")

def extract_done_section(text: str) -> str:
    """
    本文から「やったこと」だけを抽出。
    パターン:
      やったこと\n...（ここを抽出）...\n次にやること|ひとこと|$ まで
    """
    # 改行のゆらぎ/全角スペース等にやや強め
    pat = re.compile(
        r"やったこと[\t 　]*\n([\s\S]*?)(?:\n(?:次にやること|ひとこと)\b|$)",
        re.IGNORECASE
    )
    m = pat.search(text)
    if not m:
        return ""
    done = m.group(1).strip()
    # 先頭・末尾の装飾ゴミ掃除
    done = re.sub(r"\n{3,}", "\n\n", done)
    return done

def get_user_name(user_id: str) -> str:
    try:
        u = slack.users_info(user=user_id)["user"]
        # display_name > real_name の順で使用
        name = (u.get("profile", {}) or {}).get("display_name_normalized") or u.get("real_name") or user_id
        return NAME_ALIAS_MAP.get(name, name)
    except SlackApiError:
        return user_id

def get_evaluation_period(date: datetime) -> tuple[int, int]:
    """
    日付から評価期間（開始年、終了年）を取得
    例: 2025-08-12 → (2025, 2026)  # 2025年4月1日〜2026年3月31日
    """
    year = date.year
    month = date.month
    
    # 4月以降はその年の評価期間、3月以前は前年の評価期間
    if month >= EVALUATION_START_MONTH:
        return year, year + 1
    else:
        return year - 1, year

def get_evaluation_period_name(start_year: int, end_year: int) -> str:
    """評価期間の名前を生成"""
    return f"{start_year}年度評価期間 ({start_year}.4.1〜{end_year}.3.31)"

def get_evaluation_period_page_title(start_year: int, end_year: int) -> str:
    """評価期間のページタイトルを生成"""
    return f"{start_year}年度日報一覧"

def ensure_evaluation_period_page(notion_db_id: str, start_year: int, end_year: int) -> str:
    """評価期間のページがなければ作り、ページIDを返す"""
    page_title = get_evaluation_period_page_title(start_year, end_year)
    
    res = notion.databases.query(
        **{
            "database_id": notion_db_id,
            "filter": {
                "property": "メンバー名",
                "title": {"equals": page_title}
            }
        }
    )
    if res["results"]:
        return res["results"][0]["id"]

    created = notion.pages.create(
        **{
            "parent": {"database_id": notion_db_id},
            "properties": {
                "メンバー名": {"title": [{"type": "text", "text": {"content": page_title}}]}
            }
        }
    )
    return created["id"]

# ====== Notion Interactions ======
def ensure_person_page(notion_db_id: str, person_name: str) -> str:
    """DB内に人のページがなければ作り、ページIDを返す（従来の方法）"""
    res = notion.databases.query(
        **{
            "database_id": notion_db_id,
            "filter": {
                "property": "メンバー名",
                "title": {"equals": person_name}
            }
        }
    )
    if res["results"]:
        return res["results"][0]["id"]

    created = notion.pages.create(
        **{
            "parent": {"database_id": notion_db_id},
            "properties": {
                "メンバー名": {"title": [{"type": "text", "text": {"content": person_name}}]}
            }
        }
    )
    return created["id"]

def ensure_person_page_in_parent(parent_page_id: str, person_name: str) -> str:
    """親ページ内に人のページがなければ作り、ページIDを返す"""
    # 親ページの子ページを検索
    cursor = None
    while True:
        children = notion.blocks.children.list(block_id=parent_page_id, start_cursor=cursor)
        for child in children["results"]:
            if child.get("type") == "child_page":
                # ページの詳細情報を取得
                page_info = notion.pages.retrieve(child["id"])
                title = page_info.get("properties", {}).get("title", {}).get("title", [])
                if title and title[0].get("plain_text") == person_name:
                    return child["id"]
        
        if not children.get("has_more"):
            break
        cursor = children.get("next_cursor")
    
    # 見つからない場合は新しいページを作成
    created = notion.pages.create(
        **{
            "parent": {"page_id": parent_page_id},
            "properties": {
                "title": {"title": [{"type": "text", "text": {"content": person_name}}]}
            }
        }
    )
    return created["id"]

def find_toggle_block_by_title(page_id: str, title: str) -> str | None:
    """ページ直下のトグルでタイトルが完全一致するものを探す"""
    cursor = None
    while True:
        children = notion.blocks.children.list(block_id=page_id, start_cursor=cursor)
        for b in children["results"]:
            if b.get("type") == "toggle":
                rich = b["toggle"].get("rich_text", [])
                txt = "".join([t.get("plain_text", "") for t in rich])
                if txt == title:
                    return b["id"]
        if not children.get("has_more"):
            break
        cursor = children.get("next_cursor")
    return None

def list_paragraph_texts(block_id: str) -> set[str]:
    """トグル内の段落テキスト集合（重複防止用）"""
    texts = set()
    cursor = None
    while True:
        children = notion.blocks.children.list(block_id=block_id, start_cursor=cursor)
        for c in children["results"]:
            if c.get("type") == "paragraph":
                rt = c["paragraph"].get("rich_text", [])
                texts.add("".join([t.get("plain_text", "") for t in rt]))
        if not children.get("has_more"):
            break
        cursor = children.get("next_cursor")
    return texts

def append_toggle_with_paragraphs(page_id: str, title: str, lines: list[str]):
    """タイトル付きトグルを新規作成し、配下に段落を付与"""
    notion.blocks.children.append(
        block_id=page_id,
        children=[{
            "object": "block",
            "type": "toggle",
            "toggle": {
                "rich_text": [{"type": "text", "text": {"content": title}}],
                "children": [
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": line}}]
                        }
                    } for line in lines if line.strip()
                ]
            }
        }]
    )

def append_paragraphs_to_toggle(toggle_id: str, lines: list[str], existing: set[str]):
    """既存トグルに段落を追記（重複はスキップ）"""
    new_children = []
    for line in lines:
        line = line.strip()
        if not line or line in existing:
            continue
        new_children.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": line}}]
            }
        })
    if new_children:
        notion.blocks.children.append(block_id=toggle_id, children=new_children)

# ====== Slack → Notion メイン処理 ======
def run():
    print("🚀 Slack日報同期を開始します...")
    
    oldest = time.time() - LOOKBACK_DAYS * 86400
    print(f"📅 遡及期間: {LOOKBACK_DAYS}日分（{datetime.fromtimestamp(oldest, tz=JST).strftime('%Y-%m-%d %H:%M:%S')} JST 以降）")
    
    cursor = None
    messages = []
    
    print(f"📡 Slackチャンネル {SLACK_CHANNEL_ID} からメッセージを取得中...")
    
    while True:
        resp = slack.conversations_history(
            channel=SLACK_CHANNEL_ID,
            oldest=str(oldest),
            limit=200,
            cursor=cursor
        )
        batch_messages = resp.get("messages", [])
        messages.extend(batch_messages)
        print(f"📥 バッチ取得: {len(batch_messages)}件のメッセージ")
        
        if not resp.get("has_more"):
            break
        cursor = resp.get("response_metadata", {}).get("next_cursor")
    
    print(f"📊 合計 {len(messages)} 件のメッセージを取得しました")

    # 新しい順で来るので時系列に揃える
    messages.sort(key=lambda m: float(m["ts"]))
    print(f"📅 メッセージを時系列順にソートしました")

    # ユーザーごと、評価期間ごと、日付（JST）ごとに「やったこと」行を蓄積
    bucket: dict[tuple[str, int, int, str], list[str]] = {}
    
    print("\n🔍 日報メッセージを解析中...")
    
    for i, msg in enumerate(messages):
        text = msg.get("text", "").strip()
        if not text:
            continue

        print(f"\n📝 メッセージ {i+1}:")
        print(f"   ユーザー: {msg.get('user', 'bot')}")
        print(f"   タイムスタンプ: {msg.get('ts')}")
        print(f"   テキスト長: {len(text)} 文字")
        
        # テキストの最初の100文字を表示
        preview = text[:100] + "..." if len(text) > 100 else text
        print(f"   プレビュー: {preview}")

        done = extract_done_section(text)
        if not done:
            print("   ❌ 「やったこと」セクションが見つかりません")
            continue

        print(f"   ✅ 「やったこと」セクションを抽出: {len(done)} 文字")
        
        user_id = msg.get("user") or msg.get("bot_id") or "unknown"
        person = get_user_name(user_id if isinstance(user_id, str) and user_id.startswith("U") else "unknown")
        print(f"   ユーザー名: {person}")

        date_str = jst_date_str_from_ts(msg["ts"])
        print(f"   日付: {date_str}")
        
        # 評価期間を取得
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        start_year, end_year = get_evaluation_period(date_obj)
        print(f"   評価期間: {start_year}年度 ({start_year}.4.1〜{end_year}.3.31)")
        
        # 箇条書きに分割（・ / - / 行頭番号など大雑把に）
        lines = [s.strip(" ・-　") for s in re.split(r"\n+", done) if s.strip()]
        print(f"   箇条書き行数: {len(lines)}")

        if not lines:
            print("   ❌ 有効な箇条書きが見つかりません")
            continue

        bucket.setdefault((person, start_year, end_year, date_str), []).extend(lines)
        print(f"   ✅ バケットに追加: {person} - {start_year}年度 - {date_str}")

    print(f"\n📦 処理対象: {len(bucket)} 件のユーザー・日付の組み合わせ")
    
    if not bucket:
        print("❌ 処理対象の日報が見つかりませんでした")
        print("   以下の点を確認してください:")
        print("   1. Slackチャンネルに日報メッセージが投稿されているか")
        print("   2. 日報の形式が「やったこと」セクションを含んでいるか")
        print("   3. 遡及期間（3日）内にメッセージがあるか")
        return

    # Notion 反映
    print(f"\n📝 Notionデータベースに反映中...")
    
    for (person, start_year, end_year, date_str), lines in bucket.items():
        print(f"\n👤 {person} ({start_year}年度 - {date_str}) を処理中...")
        
        try:
            # 評価期間のページを取得/作成
            period_page_id = ensure_evaluation_period_page(NOTION_DB_ID, start_year, end_year)
            print(f"   ✅ 評価期間ページ取得/作成: {period_page_id}")
            
            # ユーザーページを評価期間ページの子として作成
            user_page_id = ensure_person_page_in_parent(period_page_id, person)
            print(f"   ✅ ユーザーページ取得/作成: {user_page_id}")
            
            toggle_id = find_toggle_block_by_title(user_page_id, date_str)
            if toggle_id:
                print(f"   🔄 既存の日付トグルを更新: {toggle_id}")
                existing = list_paragraph_texts(toggle_id)
                append_paragraphs_to_toggle(toggle_id, lines, existing)
                print(f"   ✅ 既存トグルに {len(lines)} 行を追加")
            else:
                print(f"   ➕ 新しい日付トグルを作成")
                append_toggle_with_paragraphs(user_page_id, date_str, lines)
                print(f"   ✅ 新しいトグルに {len(lines)} 行を追加")
                
        except Exception as e:
            print(f"   ❌ エラーが発生しました: {e}")
    
    print(f"\n🎉 同期完了！ {len(bucket)} 件の日報を処理しました")

if __name__ == "__main__":
    run()
