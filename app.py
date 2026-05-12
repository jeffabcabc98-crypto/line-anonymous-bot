from flask import Flask, request
import os
import requests
import uuid
import time
import random

from datetime import datetime, timedelta, timezone

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    ImageMessage,
    StickerMessage
)

from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    StickerMessageContent,
    ImageMessageContent,
    AudioMessageContent,
    VideoMessageContent
)

from linebot.exceptions import InvalidSignatureError
from supabase import create_client

app = Flask(__name__)

# =========================
# 隨機暱稱
# =========================
nickname_1 = [
    "星", "月", "白", "夜", "風",
    "雨", "雪", "海", "雲", "光",
    "影", "花", "羽", "夢", "霧"
]

nickname_2 = [
    "空", "辰", "羽", "夜", "風",
    "語", "海", "光", "夢", "森",
    "月", "雪", "櫻", "川", "歌"
]

emoji_list = [
    "🌙", "⭐", "🍀", "🌸", "☁️",
    "🔥", "🦋", "🌊", "❄️", "✨"
]


def generate_nickname():

    name = (
        random.choice(nickname_1) +
        random.choice(nickname_2)
    )

    emoji = random.choice(emoji_list)

    return f"{emoji} {name}"


# =========================
# 管理員設定
# =========================
ADMIN_PASSWORD = "0012477"

admin_login = {}

# =========================
# 貼圖冷卻
# =========================
sticker_cooldown = {}

# =========================
# Railway ENV
# =========================
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# =========================
# LINE
# =========================
configuration = Configuration(
    access_token=CHANNEL_ACCESS_TOKEN
)

handler = WebhookHandler(CHANNEL_SECRET)

# =========================
# Supabase
# =========================
supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


@app.route("/callback", methods=['POST'])
def callback():

    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:

        handler.handle(body, signature)

    except InvalidSignatureError:
        return 'Invalid signature', 400

    except Exception as e:

        print("Webhook錯誤")
        print(e)

    return 'OK'


# =========================
# 文字訊息
# =========================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):

    try:

        user_id = event.source.user_id
        text = event.message.text.strip()

        # =========================
        # 管理員登入
        # =========================
        if text == "管理員特權":

            admin_login[user_id] = False

            reply(
                event.reply_token,
                "🔐 請輸入管理員密碼\n格式：\n密碼:0012477"
            )

            return

        # =========================
        # 管理員密碼驗證
        # =========================
        if text.startswith("密碼:"):

            password = text.replace("密碼:", "").strip()

            if password == ADMIN_PASSWORD:

                admin_login[user_id] = True

                reply(
                    event.reply_token,
                    "🛠️ 管理員功能\n\n"
                    "1️⃣ 查看等待人數\n"
                    "2️⃣ 查看聊天中人數\n"
                    "3️⃣ 查看封鎖排行榜\n"
                    "4️⃣ 查看最近聊天紀錄\n"
                    "5️⃣ 封鎖使用者\n"
                    "6️⃣ 解封使用者\n"
                    "7️⃣ 查看停權名單"
                )

            else:

                reply(event.reply_token, "❌ 密碼錯誤")

            return
                    # =========================
        # 查看等待人數
        # =========================
        if text == "1" or text == "1️⃣ 查看等待人數":

            if not admin_login.get(user_id):
                return

            waiting = supabase.table("waiting_users") \
                .select("*", count="exact") \
                .execute()

            count = waiting.count

            reply(
                event.reply_token,
                f"⏳ 目前等待配對：{count} 人"
            )

            return

        # =========================
        # 查看聊天中人數
        # =========================
        if text == "2" or text == "2️⃣ 查看聊天中人數":

            if not admin_login.get(user_id):
                return

            chatting = supabase.table("chat_pairs") \
                .select("*", count="exact") \
                .execute()

            count = chatting.count // 2

            reply(
                event.reply_token,
                f"💬 目前聊天中：{count} 組"
            )

            return

        # =========================
        # 查看封鎖排行榜
        # =========================
        if text == "3" or text == "3️⃣ 查看封鎖排行榜":

            if not admin_login.get(user_id):
                return

            result = supabase.table("blacklist") \
                .select("blocked_user_id") \
                .execute()

            if not result.data:

                reply(event.reply_token, "目前沒有封鎖資料")
                return

            counter = {}

            for row in result.data:

                uid = row["blocked_user_id"]

                counter[uid] = counter.get(uid, 0) + 1

            sorted_users = sorted(
                counter.items(),
                key=lambda x: x[1],
                reverse=True
            )

            msg = "🚨 封鎖排行榜\n\n"

            for uid, count in sorted_users[:10]:

                msg += f"{uid[:12]}... 被封鎖 {count} 次\n"

            reply(event.reply_token, msg)

            return

        # =========================
        # 查看最近聊天紀錄
        # =========================
        if text == "4" or text == "4️⃣ 查看最近聊天紀錄":

            if not admin_login.get(user_id):
                return

            logs = supabase.table("chat_logs") \
                .select("*") \
                .order("created_at", desc=True) \
                .limit(10) \
                .execute()

            if not logs.data:

                reply(event.reply_token, "目前沒有聊天紀錄")
                return

            msg = "🧾 最近聊天紀錄\n\n"

            for row in logs.data:

                name = row.get("sender_name", "未知")
                message = row.get("message", "")

                msg += f"{name}：{message}\n\n"

            reply(event.reply_token, msg[:5000])

            return

        # =========================
        # 管理員封號
        # =========================
        if text.startswith("封號 "):

            if not admin_login.get(user_id):
                return

            try:

                target = text.replace("封號 ", "").strip()

                check = supabase.table("banned_users") \
                    .select("*") \
                    .eq("user_id", target) \
                    .execute()

                if check.data:

                    reply(event.reply_token, "此人已被封號")
                    return

                supabase.table("banned_users").insert({
                    "user_id": target,
                    "reason": "管理員封號"
                }).execute()

                reply(event.reply_token, "✅ 已成功封號")

            except Exception as e:

                print(e)
                reply(event.reply_token, "封號失敗")

            return

        # =========================
        # 管理員解封
        # =========================
        if text.startswith("解封 "):

            if not admin_login.get(user_id):
                return

            try:

                target = text.replace("解封 ", "").strip()

                supabase.table("banned_users") \
                    .delete() \
                    .eq("user_id", target) \
                    .execute()

                reply(event.reply_token, "✅ 已解除封號")

            except Exception as e:

                print(e)
                reply(event.reply_token, "解封失敗")

            return
                    # =========================
        # 查看停權名單
        # =========================
        if text == "7" or text == "7️⃣ 查看停權名單":

            if not admin_login.get(user_id):
                return

            result = supabase.table("banned_users") \
                .select("*") \
                .execute()

            if not result.data:

                reply(event.reply_token, "目前沒有停權名單")
                return

            msg = "🚫 停權名單\n\n"

            for row in result.data:

                uid = row["user_id"]
                reason = row["reason"]

                msg += f"{uid[:12]}...\n原因：{reason}\n\n"

            reply(event.reply_token, msg[:5000])

            return

        # =========================
        # 管理員封號檢查
        # =========================
        banned = supabase.table("banned_users") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if banned.data:

            reason = banned.data[0]["reason"]

            reply(
                event.reply_token,
                f"🚫 你已被停權\n原因：{reason}"
            )

            return

        # =========================
        # Emoji 表情貼
        # =========================
        if hasattr(event.message, "emojis") and event.message.emojis:

            now = time.time()

            if user_id in sticker_cooldown:

                diff = now - sticker_cooldown[user_id]

                if diff < 5:

                    remain = round(5 - diff, 1)

                    reply(
                        event.reply_token,
                        f"⏳ 你的手速太快了，請 {remain} 秒後再試"
                    )

                    return

            sticker_cooldown[user_id] = now

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if result.data:

                partner = result.data[0]["partner_id"]
                nickname = result.data[0]["nickname"]

                # 聊天紀錄
                supabase.table("chat_logs").insert({
                    "sender_id": user_id,
                    "receiver_id": partner,
                    "sender_name": nickname,
                    "message_type": "emoji",
                    "message": text
                }).execute()

                push_text(
                    partner,
                    f"{nickname}：{text}"
                )

                for emoji in event.message.emojis:

                    product_id = emoji.product_id
                    emoji_id = emoji.emoji_id

                    emoji_url = (
                        f"https://stickershop.line-scdn.net/"
                        f"sticonshop/v1/sticon/{product_id}/iPhone/{emoji_id}.png"
                    )

                    try:

                        with ApiClient(configuration) as api_client:

                            line_bot_api = MessagingApi(api_client)

                            line_bot_api.push_message(
                                PushMessageRequest(
                                    to=partner,
                                    messages=[
                                        ImageMessage(
                                            original_content_url=emoji_url,
                                            preview_image_url=emoji_url
                                        )
                                    ]
                                )
                            )

                    except Exception as e:
                        print(e)

            return
                    # =========================
        # 封鎖名單
        # =========================
        if text == "封鎖名單":

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                reply(event.reply_token, "✅ 目前沒有封鎖任何人")
                return

            msg = "🚫 封鎖名單：\n\n"

            for i, row in enumerate(result.data, start=1):

                nickname = row["nickname"]

                msg += f"{i}. {nickname}\n"

            reply(event.reply_token, msg)

            return

        # =========================
        # 解除封鎖選單
        # =========================
        if text == "解除封鎖":

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                reply(event.reply_token, "✅ 目前沒有封鎖任何人")
                return

            msg = "🔓 請選擇要解除封鎖的人：\n\n"

            for i, row in enumerate(result.data, start=1):

                nickname = row["nickname"]

                msg += f"{i}. {nickname}\n"

            msg += "\n輸入：\n解除 編號"

            reply(event.reply_token, msg)

            return

        # =========================
        # 單獨解除
        # =========================
        if text.startswith("解除 "):

            try:

                parts = text.split()

                if len(parts) < 2:

                    reply(event.reply_token, "格式：解除 編號")
                    return

                index = int(parts[1]) - 1

                result = supabase.table("blacklist") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .execute()

                if not result.data:

                    reply(event.reply_token, "沒有封鎖名單")
                    return

                if index < 0 or index >= len(result.data):

                    reply(event.reply_token, "編號不存在")
                    return

                target = result.data[index]

                nickname = target["nickname"]

                supabase.table("blacklist") \
                    .delete() \
                    .eq("id", target["id"]) \
                    .execute()

                reply(
                    event.reply_token,
                    f"✅ 已解除封鎖 {nickname}"
                )

            except Exception as e:

                print(e)

                reply(event.reply_token, "解除失敗")

            return

        # =========================
        # 封鎖對方
        # =========================
        if text == "封鎖":

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if not result.data:

                reply(event.reply_token, "目前沒有聊天對象")
                return

            partner = result.data[0]["partner_id"]
            nickname = result.data[0]["partner_nickname"]

            # 檢查是否已封鎖過
            already_blocked = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .eq("blocked_user_id", partner) \
                .execute()

            if already_blocked.data:

                reply(
                    event.reply_token,
                    "⚠️ 你已經封鎖過這位使用者"
                )

                return
                            # 新增封鎖
            supabase.table("blacklist").insert({
                "user_id": user_id,
                "blocked_user_id": partner,
                "nickname": nickname
            }).execute()

            # =========================
            # 自動封號檢查
            # =========================
            block_count = supabase.table("blacklist") \
                .select("*", count="exact") \
                .eq("blocked_user_id", partner) \
                .execute()

            count = block_count.count

            print("被封鎖次數：", count)

            if count >= 10:

                check_ban = supabase.table("banned_users") \
                    .select("*") \
                    .eq("user_id", partner) \
                    .limit(1) \
                    .execute()

                if not check_ban.data:

                    supabase.table("banned_users").insert({
                        "user_id": partner,
                        "reason": "被超過10位使用者封鎖"
                    }).execute()

                    print("已自動封號")

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", partner) \
                .execute()

            reply(
                event.reply_token,
                f"🚫 已封鎖 {nickname}"
            )

            try:
                push_text(partner, "⚠️ 對方已離開聊天")
            except:
                pass

            return

        # =========================
        # 開始配對
        # =========================
        if text == "開始":

            check_waiting = supabase.table("waiting_users") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if check_waiting.data:

                reply(event.reply_token, "⏳ 你已經在等待配對中了")
                return

            check_chat = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if check_chat.data:

                reply(event.reply_token, "💬 你目前已經在聊天中了")
                return

            waiting_users = supabase.table("waiting_users") \
                .select("*") \
                .neq("user_id", user_id) \
                .execute()

            partner = None

            for row in waiting_users.data:

                target = row["user_id"]

                check1 = supabase.table("blacklist") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .eq("blocked_user_id", target) \
                    .execute()

                check2 = supabase.table("blacklist") \
                    .select("*") \
                    .eq("user_id", target) \
                    .eq("blocked_user_id", user_id) \
                    .execute()

                if check1.data or check2.data:
                    continue

                partner = target
                break

            if partner:

                one_hour_ago = datetime.now(
                    timezone.utc
                ) - timedelta(hours=1)

                recent = supabase.table("recent_pairs") \
                    .select("*") \
                    .or_(
                        f"and(user1.eq.{user_id},user2.eq.{partner}),"
                        f"and(user1.eq.{partner},user2.eq.{user_id})"
                    ) \
                    .gte(
                        "created_at",
                        one_hour_ago.isoformat()
                    ) \
                    .execute()
                if recent.data:

                reply(
                    event.reply_token,
                    "⏳ 正在尋找新的聊天對象..."
                )

                return

            supabase.table("waiting_users") \
                .delete() \
                .eq("user_id", partner) \
                .execute()

            nickname1 = generate_nickname()
            nickname2 = generate_nickname()

            supabase.table("chat_pairs").insert([
                {
                    "user_id": user_id,
                    "partner_id": partner,
                    "nickname": nickname1,
                    "partner_nickname": nickname2
                },
                {
                    "user_id": partner,
                    "partner_id": user_id,
                    "nickname": nickname2,
                    "partner_nickname": nickname1
                }
            ]).execute()

            supabase.table("recent_pairs").insert({
                "user1": user_id,
                "user2": partner
            }).execute()

            reply(
                event.reply_token,
                f"✅ 配對成功！\n你的暱稱：{nickname1}"
            )

            push_text(
                partner,
                f"✅ 配對成功！\n你的暱稱：{nickname2}"
            )

        else:

            supabase.table("waiting_users") \
                .upsert({
                    "user_id": user_id
                }) \
                .execute()

            reply(event.reply_token, "⏳ 等待配對中...")

        return

    # =========================
    # 離開聊天
    # =========================
    if text == "離開":

        result = supabase.table("chat_pairs") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if not result.data:

            reply(event.reply_token, "目前沒有聊天對象")
            return

        partner = result.data[0]["partner_id"]

        supabase.table("chat_pairs") \
            .delete() \
            .eq("user_id", user_id) \
            .execute()

        supabase.table("chat_pairs") \
            .delete() \
            .eq("user_id", partner) \
            .execute()

        try:
            push_text(
                partner,
                "⚠️ 對方已離開聊天"
            )
        except:
            pass

        reply(event.reply_token, "✅ 你已離開聊天")

        return

    # =========================
    # 一般聊天
    # =========================
    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()

    if result.data:

        partner = result.data[0]["partner_id"]
        nickname = result.data[0]["nickname"]

        # 聊天紀錄
        supabase.table("chat_logs").insert({
            "sender_id": user_id,
            "receiver_id": partner,
            "sender_name": nickname,
            "message_type": "text",
            "message": text
        }).execute()

        push_text(
            partner,
            f"{nickname}：{text}"
        )

    else:

        reply(
            event.reply_token,
            "輸入「開始」開始匿名聊天"
        )

except Exception as e:

    print("文字錯誤")
    print(e)


# =========================
# 貼圖
# =========================
@handler.add(MessageEvent, message=StickerMessageContent)
def handle_sticker(event):

    try:

        user_id = event.source.user_id

        result = supabase.table("chat_pairs") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if not result.data:
            return

        partner = result.data[0]["partner_id"]

        package_id = str(event.message.package_id)
        sticker_id = str(event.message.sticker_id)

        # 聊天紀錄
        supabase.table("chat_logs").insert({
            "sender_id": user_id,
            "receiver_id": partner,
            "sender_name": "貼圖",
            "message_type": "sticker",
            "message": sticker_id
        }).execute()
                with ApiClient(configuration) as api_client:

            line_bot_api = MessagingApi(api_client)

            line_bot_api.push_message(
                PushMessageRequest(
                    to=partner,
                    messages=[
                        StickerMessage(
                            package_id=package_id,
                            sticker_id=sticker_id
                        )
                    ]
                )
            )

    except Exception as e:

        print("貼圖錯誤")
        print(e)


# =========================
# 圖片
# =========================
@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):

    try:

        user_id = event.source.user_id

        result = supabase.table("chat_pairs") \
            .select("*") \
            .eq("user_id", user_id) \
            .limit(1) \
            .execute()

        if not result.data:
            return

        partner = result.data[0]["partner_id"]
        nickname = result.data[0]["nickname"]

        message_id = event.message.id

        headers = {
            "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
        }

        url = (
            f"https://api-data.line.me/v2/bot/message/"
            f"{message_id}/content"
        )

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return

        filename = f"{uuid.uuid4()}.jpg"

        supabase.storage.from_("chat-images").upload(
            filename,
            response.content,
            {"content-type": "image/jpeg"}
        )

        image_url = supabase.storage \
            .from_("chat-images") \
            .get_public_url(filename)

        if isinstance(image_url, dict):
            image_url = image_url["publicUrl"]

        # 聊天紀錄
        supabase.table("chat_logs").insert({
            "sender_id": user_id,
            "receiver_id": partner,
            "sender_name": nickname,
            "message_type": "image",
            "message": image_url
        }).execute()

        push_text(
            partner,
            f"🖼️ {nickname} 傳送了一張圖片"
        )

        with ApiClient(configuration) as api_client:

            line_bot_api = MessagingApi(api_client)

            line_bot_api.push_message(
                PushMessageRequest(
                    to=partner,
                    messages=[
                        ImageMessage(
                            original_content_url=image_url,
                            preview_image_url=image_url
                        )
                    ]
                )
            )

    except Exception as e:

        print("圖片錯誤")
        print(e)


# =========================
# Reply
# =========================
def reply(reply_token, text):

    try:

        with ApiClient(configuration) as api_client:

            line_bot_api = MessagingApi(api_client)

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=reply_token,
                    messages=[
                        TextMessage(text=text)
                    ]
                )
            )

    except Exception as e:
        print(e)


# =========================
# Push Text
# =========================
def push_text(user_id, text):

    try:

        with ApiClient(configuration) as api_client:

            line_bot_api = MessagingApi(api_client)

            line_bot_api.push_message(
                PushMessageRequest(
                    to=user_id,
                    messages=[
                        TextMessage(text=text)
                    ]
                )
            )

    except Exception as e:
        print(e)


# =========================
# Run
# =========================
if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True
    )
