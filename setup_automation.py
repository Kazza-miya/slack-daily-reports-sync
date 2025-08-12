#!/usr/bin/env python3
"""
Slack日報同期システムの自動セットアップスクリプト
"""

import os
import sys
import subprocess
import json
import requests
from pathlib import Path

# ====== 設定情報 ======
GITHUB_TOKEN = None  # ユーザーが入力
REPO_NAME = "slack-daily-reports-sync"
REPO_OWNER = None  # ユーザーが入力

# APIトークンはユーザー入力または環境変数から取得
SLACK_BOT_TOKEN = None
SLACK_CHANNEL_ID = None
NOTION_TOKEN = None
NOTION_DB_ID = None

def print_step(step_num, title):
    print(f"\n{'='*50}")
    print(f"ステップ {step_num}: {title}")
    print(f"{'='*50}")

def run_command(cmd, description):
    print(f"\n📋 {description}")
    print(f"実行コマンド: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ 成功")
            return result.stdout
        else:
            print(f"❌ エラー: {result.stderr}")
            return None
    except Exception as e:
        print(f"❌ 例外: {e}")
        return None

def get_api_credentials():
    """API認証情報をユーザーから取得"""
    global SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, NOTION_TOKEN, NOTION_DB_ID
    
    print("\n🔐 API認証情報を入力してください:")
    
    # 環境変数から取得を試行、なければユーザー入力
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN") or input("Slack Bot Token (xoxb-...): ").strip()
    SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID") or input("Slack Channel ID (C...): ").strip()
    NOTION_TOKEN = os.getenv("NOTION_TOKEN") or input("Notion Token (secret_...): ").strip()
    NOTION_DB_ID = os.getenv("NOTION_DB_ID") or input("Notion Database ID: ").strip()
    
    if not all([SLACK_BOT_TOKEN, SLACK_CHANNEL_ID, NOTION_TOKEN, NOTION_DB_ID]):
        print("❌ 全ての認証情報が必要です")
        return False
    
    return True

def create_github_repo():
    """GitHubリポジトリを作成"""
    print_step(1, "GitHubリポジトリの作成")
    
    # GitHub CLIがインストールされているか確認
    if not run_command("gh --version", "GitHub CLIの確認"):
        print("❌ GitHub CLIがインストールされていません")
        print("インストール方法: https://cli.github.com/")
        return False
    
    # ログイン確認
    if not run_command("gh auth status", "GitHub認証状態の確認"):
        print("❌ GitHubにログインしていません")
        print("実行してください: gh auth login")
        return False
    
    # リポジトリ作成
    repo_url = run_command(f"gh repo create {REPO_NAME} --public --source=. --remote=origin --push", 
                          "GitHubリポジトリの作成とプッシュ")
    
    if repo_url:
        print(f"✅ リポジトリ作成完了: {repo_url}")
        return True
    return False

def setup_github_secrets():
    """GitHub Secretsを設定"""
    print_step(2, "GitHub Secretsの設定")
    
    secrets = {
        "SLACK_BOT_TOKEN": SLACK_BOT_TOKEN,
        "SLACK_CHANNEL_ID": SLACK_CHANNEL_ID,
        "NOTION_TOKEN": NOTION_TOKEN,
        "NOTION_DB_ID": NOTION_DB_ID
    }
    
    for name, value in secrets.items():
        print(f"\n🔐 {name} を設定中...")
        result = run_command(f"gh secret set {name} --body '{value}'", f"{name}の設定")
        if not result:
            print(f"❌ {name}の設定に失敗しました")
            return False
    
    print("✅ 全てのSecrets設定完了")
    return True

def check_notion_database():
    """Notionデータベースの構造を確認"""
    print_step(3, "Notionデータベースの確認")
    
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    try:
        # データベース情報を取得
        response = requests.get(f"https://api.notion.com/v1/databases/{NOTION_DB_ID}", headers=headers)
        
        if response.status_code == 200:
            db_info = response.json()
            print("✅ Notionデータベースにアクセス成功")
            
            # プロパティを確認
            properties = db_info.get("properties", {})
            name_property = None
            
            for prop_name, prop_info in properties.items():
                if prop_info.get("type") == "title":
                    name_property = prop_name
                    break
            
            if name_property:
                print(f"✅ Titleプロパティ名: '{name_property}'")
                if name_property != "Name":
                    print(f"⚠️  注意: Titleプロパティ名が'Name'ではありません")
                    print(f"   現在: '{name_property}' → コード修正が必要")
            else:
                print("❌ Titleプロパティが見つかりません")
                return False
                
        else:
            print(f"❌ Notionデータベースアクセス失敗: {response.status_code}")
            print(f"   エラー: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Notion API呼び出しエラー: {e}")
        return False
    
    return True

def check_slack_bot():
    """Slack Botの権限を確認"""
    print_step(4, "Slack Botの確認")
    
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        # Bot情報を取得
        response = requests.get("https://slack.com/api/auth.test", headers=headers)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                print("✅ Slack Bot認証成功")
                print(f"   ボット名: {result.get('user')}")
                print(f"   チーム: {result.get('team')}")
                
                # チャンネル情報を取得
                channel_response = requests.get(
                    f"https://slack.com/api/conversations.info?channel={SLACK_CHANNEL_ID}",
                    headers=headers
                )
                
                if channel_response.status_code == 200:
                    channel_result = channel_response.json()
                    if channel_result.get("ok"):
                        print(f"✅ チャンネルアクセス成功: {channel_result['channel']['name']}")
                    else:
                        print(f"❌ チャンネルアクセス失敗: {channel_result.get('error')}")
                        print("   Botをチャンネルに招待してください: /invite @ボット名")
                else:
                    print("❌ チャンネル情報取得失敗")
                    
            else:
                print(f"❌ Slack Bot認証失敗: {result.get('error')}")
                return False
        else:
            print(f"❌ Slack API呼び出し失敗: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Slack API呼び出しエラー: {e}")
        return False
    
    return True

def test_workflow():
    """GitHub Actionsワークフローをテスト実行"""
    print_step(5, "GitHub Actionsワークフローのテスト実行")
    
    print("🔄 ワークフローを手動実行中...")
    result = run_command("gh workflow run 'Sync Slack Daily Reports to Notion'", "ワークフロー実行")
    
    if result:
        print("✅ ワークフロー実行開始")
        print(f"📊 実行状況を確認: https://github.com/{REPO_OWNER}/{REPO_NAME}/actions")
    else:
        print("❌ ワークフロー実行失敗")
        return False
    
    return True

def main():
    print("🚀 Slack日報同期システムの自動セットアップを開始します")
    
    # 必要な情報を取得
    global REPO_OWNER
    
    print("\n📝 必要な情報を入力してください:")
    REPO_OWNER = input("GitHubユーザー名または組織名: ").strip()
    
    if not REPO_OWNER:
        print("❌ GitHubユーザー名が必要です")
        return
    
    # API認証情報を取得
    if not get_api_credentials():
        print("❌ API認証情報の取得に失敗しました")
        return
    
    # 1. GitHubリポジトリ作成
    if not create_github_repo():
        print("❌ GitHubリポジトリ作成に失敗しました")
        return
    
    # 2. GitHub Secrets設定
    if not setup_github_secrets():
        print("❌ GitHub Secrets設定に失敗しました")
        return
    
    # 3. Notionデータベース確認
    if not check_notion_database():
        print("❌ Notionデータベース確認に失敗しました")
        return
    
    # 4. Slack Bot確認
    if not check_slack_bot():
        print("❌ Slack Bot確認に失敗しました")
        return
    
    # 5. ワークフローテスト
    if not test_workflow():
        print("❌ ワークフローテストに失敗しました")
        return
    
    print("\n🎉 セットアップ完了！")
    print(f"📊 ダッシュボード: https://github.com/{REPO_OWNER}/{REPO_NAME}")
    print(f"🔧 Actions: https://github.com/{REPO_OWNER}/{REPO_NAME}/actions")
    print("\n📋 次のステップ:")
    print("1. GitHub Actionsの実行ログを確認")
    print("2. Notionデータベースで結果を確認")
    print("3. 必要に応じてSlack Botをチャンネルに招待")

if __name__ == "__main__":
    main()
