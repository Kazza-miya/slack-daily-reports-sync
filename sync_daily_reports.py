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

# ====== Notion Interactions ======
def ensure_person_page(notion_db_id: str, person_name: str) -> str:
    """DB内に人のページがなければ作り、ページIDを返す"""
    res = notion.databases.query(
        **{
            "database_id": notion_db_id,
            "filter": {
                "property": "Name",
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
                "Name": {"title": [{"type": "text", "text": {"content": person_name}}]}
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
    oldest = time.time() - LOOKBACK_DAYS * 86400
    cursor = None
    messages = []
    while True:
        resp = slack.conversations_history(
            channel=SLACK_CHANNEL_ID,
            oldest=str(oldest),
            limit=200,
            cursor=cursor
        )
        messages.extend(resp.get("messages", []))
        if not resp.get("has_more"):
            break
        cursor = resp.get("response_metadata", {}).get("next_cursor")

    # 新しい順で来るので時系列に揃える
    messages.sort(key=lambda m: float(m["ts"]))

    # ユーザーごと、日付（JST）ごとに「やったこと」行を蓄積
    bucket: dict[tuple[str, str], list[str]] = {}

    for msg in messages:
        text = msg.get("text", "").strip()
        if not text:
            continue

        done = extract_done_section(text)
        if not done:
            continue

        user_id = msg.get("user") or msg.get("bot_id") or "unknown"
        person = get_user_name(user_id if isinstance(user_id, str) and user_id.startswith("U") else "unknown")

        date_str = jst_date_str_from_ts(msg["ts"])
        # 箇条書きに分割（・ / - / 行頭番号など大雑把に）
        lines = [s.strip(" ・-　") for s in re.split(r"\n+", done) if s.strip()]

        if not lines:
            continue

        bucket.setdefault((person, date_str), []).extend(lines)

    # Notion 反映
    for (person, date_str), lines in bucket.items():
        page_id = ensure_person_page(NOTION_DB_ID, person)
        toggle_id = find_toggle_block_by_title(page_id, date_str)
        if toggle_id:
            existing = list_paragraph_texts(toggle_id)
            append_paragraphs_to_toggle(toggle_id, lines, existing)
        else:
            append_toggle_with_paragraphs(page_id, date_str, lines)

if __name__ == "__main__":
    run()
