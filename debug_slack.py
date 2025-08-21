import os
import time
from datetime import datetime
import pytz
from slack_sdk.web import WebClient
from slack_sdk.errors import SlackApiError

# 環境変数から取得
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID")

print("🔍 Slack API デバッグ開始")
print(f"Bot Token: {SLACK_BOT_TOKEN[:20]}..." if SLACK_BOT_TOKEN else "❌ Bot Token なし")
print(f"Channel ID: {SLACK_CHANNEL_ID}")

if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
    print("❌ 環境変数が不足しています")
    exit(1)

slack = WebClient(token=SLACK_BOT_TOKEN)

try:
    # 1. Bot認証テスト
    print("\n1️⃣ Bot認証テスト")
    auth_test = slack.auth_test()
    print(f"✅ 認証成功: {auth_test['user']} ({auth_test['user_id']})")
    print(f"   チーム: {auth_test['team']} ({auth_test['team_id']})")
    
    # 2. チャンネル情報取得
    print("\n2️⃣ チャンネル情報取得")
    channel_info = slack.conversations_info(channel=SLACK_CHANNEL_ID)
    channel = channel_info['channel']
    print(f"✅ チャンネル取得成功: {channel['name']} ({channel['id']})")
    print(f"   メンバー数: {channel.get('num_members', '不明')}")
    print(f"   プライベート: {channel.get('is_private', False)}")
    print(f"   アーカイブ済み: {channel.get('is_archived', False)}")
    
    # 3. Botがチャンネルに参加しているか確認
    print("\n3️⃣ Botのチャンネル参加状況")
    try:
        # チャンネルのメンバー一覧を取得
        members = slack.conversations_members(channel=SLACK_CHANNEL_ID)
        bot_user_id = auth_test['user_id']
        is_member = bot_user_id in [m['id'] for m in members['members']]
        print(f"✅ Bot ({bot_user_id}) はチャンネルに{'参加済み' if is_member else '未参加'}")
        
        if not is_member:
            print("⚠️  Botをチャンネルに招待する必要があります")
            
    except SlackApiError as e:
        print(f"❌ メンバー一覧取得エラー: {e.response['error']}")
    
    # 4. 最新メッセージの取得テスト
    print("\n4️⃣ 最新メッセージ取得テスト")
    
    # 過去90日分のメッセージを取得
    oldest = time.time() - 90 * 86400
    print(f"   遡及期間: 90日分（{datetime.fromtimestamp(oldest, tz=pytz.timezone('Asia/Tokyo')).strftime('%Y-%m-%d %H:%M:%S')} JST 以降）")
    
    history = slack.conversations_history(
        channel=SLACK_CHANNEL_ID,
        oldest=str(oldest),
        limit=10
    )
    
    messages = history.get('messages', [])
    print(f"✅ メッセージ取得成功: {len(messages)}件")
    
    if messages:
        print("   最新5件のメッセージ:")
        for i, msg in enumerate(messages[:5]):
            ts = float(msg['ts'])
            dt = datetime.fromtimestamp(ts, tz=pytz.timezone('Asia/Tokyo'))
            user = msg.get('user', msg.get('bot_id', 'unknown'))
            text = msg.get('text', '')[:50] + '...' if len(msg.get('text', '')) > 50 else msg.get('text', '')
            print(f"   {i+1}. {dt.strftime('%Y-%m-%d %H:%M')} - {user}: {text}")
    else:
        print("❌ メッセージが見つかりません")
        
        # より長期間で試行
        print("\n   過去1年分で再試行...")
        oldest_1year = time.time() - 365 * 86400
        history_1year = slack.conversations_history(
            channel=SLACK_CHANNEL_ID,
            oldest=str(oldest_1year),
            limit=5
        )
        messages_1year = history_1year.get('messages', [])
        print(f"   1年分の結果: {len(messages_1year)}件")
        
        if messages_1year:
            print("   最新メッセージ:")
            latest = messages_1year[0]
            ts = float(latest['ts'])
            dt = datetime.fromtimestamp(ts, tz=pytz.timezone('Asia/Tokyo'))
            print(f"   {dt.strftime('%Y-%m-%d %H:%M')} - {latest.get('user', 'bot')}")
    
    # 5. Botの権限確認
    print("\n5️⃣ Bot権限確認")
    try:
        # チャンネル履歴の読み取り権限をテスト
        test_history = slack.conversations_history(channel=SLACK_CHANNEL_ID, limit=1)
        print("✅ チャンネル履歴読み取り権限: OK")
    except SlackApiError as e:
        print(f"❌ チャンネル履歴読み取り権限エラー: {e.response['error']}")
    
except SlackApiError as e:
    print(f"❌ Slack API エラー: {e.response['error']}")
    if e.response['error'] == 'channel_not_found':
        print("   チャンネルが見つかりません。チャンネルIDを確認してください。")
    elif e.response['error'] == 'not_in_channel':
        print("   Botがチャンネルに参加していません。")
    elif e.response['error'] == 'missing_scope':
        print("   Botの権限が不足しています。")
        print("   必要な権限: channels:history, channels:read, users:read")
    elif e.response['error'] == 'invalid_auth':
        print("   Bot Tokenが無効です。")
    elif e.response['error'] == 'token_revoked':
        print("   Bot Tokenが取り消されています。")

print("\n🔍 デバッグ完了")
