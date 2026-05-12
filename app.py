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
    StickerMessage,
    AudioMessage,
    VideoMessage
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
# 冷卻時間
# =========================
sticker_cooldown = {}

# =========================
# ENV
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
        print(e)

    return 'OK'


# =========================
# Reply
# =========================
def reply(reply_token, text):

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


# =========================
# Push Text
# =========================
def push_text(user_id, text):

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


# =========================
# 上傳 LINE 內容
# =========================
def get_content(message_id):

    headers = {
        "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
    }

    url = (
        f"https://api-data.line.me/v2/bot/message/"
        f"{message_id}/content"
    )

    response = requests.get(url, headers=headers)

    return response.content


# =========================
# 檢查聊天對象
# =========================
def get_partner(user_id):

    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .limit(1) \
        .execute()

    if not result.data:
        return None

    return result.data[0]


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
        # 管理員密碼
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
                    "5️⃣ 封號 USER_ID\n"
                    "6️⃣ 解封 USER_ID\n"
                    "7️⃣ 查看停權名單"
                )

            else:
                reply(event.reply_token, "❌ 密碼錯誤")

            return

        # =========================
        # 管理員功能
        # =========================
        if text == "1":

            if admin_login.get(user_id):

                waiting = supabase.table("waiting_users") \
                    .select("*", count="exact") \
                    .execute()

                reply(
                    event.reply_token,
                    f"⏳ 等待配對：{waiting.count} 人"
                )

            return

        if text == "2":

            if admin_login.get(user_id):

                chatting = supabase.table("chat_pairs") \
                    .select("*", count="exact") \
                    .execute()

                count = chatting.count // 2

                reply(
                    event.reply_token,
                    f"💬 聊天中：{count} 組"
                )

            return

        if text == "3":

            if admin_login.get(user_id):

                result = supabase.table("blacklist") \
                    .select("blocked_user_id") \
                    .execute()

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
                    msg += f"{uid[:12]}... {count} 次\n"

                reply(event.reply_token, msg)

            return

        if text == "4":

            if admin_login.get(user_id):

                logs = supabase.table("chat_logs") \
                    .select("*") \
                    .order("created_at", desc=True) \
                    .limit(10) \
                    .execute()

                msg = "🧾 最近聊天紀錄\n\n"

                for row in logs.data:

                    name = row.get("sender_name", "未知")
                    message = row.get("message", "")

                    msg += f"{name}：{message}\n\n"

                reply(event.reply_token, msg[:5000])

            return

        if text.startswith("封號 "):

            if admin_login.get(user_id):

                target = text.replace("封號 ", "").strip()

                supabase.table("banned_users").insert({
                    "user_id": target,
                    "reason": "管理員封號"
                }).execute()

                reply(event.reply_token, "✅ 已封號")

            return

        if text.startswith("解封 "):

            if admin_login.get(user_id):

                target = text.replace("解封 ", "").strip()

                supabase.table("banned_users") \
                    .delete() \
                    .eq("user_id", target) \
                    .execute()

                reply(event.reply_token, "✅ 已解封")

            return

        if text == "7":

            if admin_login.get(user_id):

                result = supabase.table("banned_users") \
                    .select("*") \
                    .execute()

                msg = "🚫 停權名單\n\n"

                for row in result.data:
                    msg += f"{row['user_id'][:12]}...\n"

                reply(event.reply_token, msg)

            return

        # =========================
        # 停權檢查
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
        # 封鎖名單
        # =========================
        if text == "封鎖名單":

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                reply(event.reply_token, "目前沒有封鎖任何人")
                return

            msg = "🚫 封鎖名單\n\n"

            for i, row in enumerate(result.data, start=1):
                msg += f"{i}. {row['nickname']}\n"

            reply(event.reply_token, msg)
            return

        # =========================
        # 解除封鎖
        # =========================
        if text == "解除封鎖":

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if not result.data:

                reply(event.reply_token, "目前沒有封鎖任何人")
                return

            msg = "🔓 解除封鎖列表\n\n"

            for i, row in enumerate(result.data, start=1):
                msg += f"{i}. {row['nickname']}\n"

            msg += "\n輸入：解除 編號"

            reply(event.reply_token, msg)
            return

        if text.startswith("解除 "):

            parts = text.split()

            if len(parts) < 2:
                return

            index = int(parts[1]) - 1

            result = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            target = result.data[index]

            supabase.table("blacklist") \
                .delete() \
                .eq("id", target["id"]) \
                .execute()

            reply(event.reply_token, "✅ 已解除封鎖")
            return

        # =========================
        # 開始配對
        # =========================
        if text == "開始":

            already = get_partner(user_id)

            if already:

                reply(event.reply_token, "你已經在聊天中了")
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

                one_hour_ago = datetime.now(
                    timezone.utc
                ) - timedelta(hours=1)

                recent = supabase.table("recent_pairs") \
                    .select("*") \
                    .or_(
                        f"and(user1.eq.{user_id},user2.eq.{target}),"
                        f"and(user1.eq.{target},user2.eq.{user_id})"
                    ) \
                    .gte(
                        "created_at",
                        one_hour_ago.isoformat()
                    ) \
                    .execute()

                if recent.data:
                    continue

                partner = target
                break

            if partner:

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
                    f"✅ 配對成功\n你的暱稱：{nickname1}"
                )

                push_text(
                    partner,
                    f"✅ 配對成功\n你的暱稱：{nickname2}"
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

            result = get_partner(user_id)

            if not result:

                reply(event.reply_token, "目前沒有聊天對象")
                return

            partner = result["partner_id"]

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", partner) \
                .execute()

            reply(event.reply_token, "✅ 已離開聊天")

            push_text(partner, "⚠️ 對方已離開聊天")

            return

        # =========================
        # 封鎖對方
        # =========================
        if text == "封鎖":

            result = get_partner(user_id)

            if not result:

                reply(event.reply_token, "目前沒有聊天對象")
                return

            partner = result["partner_id"]
            nickname = result["partner_nickname"]

            already = supabase.table("blacklist") \
                .select("*") \
                .eq("user_id", user_id) \
                .eq("blocked_user_id", partner) \
                .execute()

            if already.data:

                reply(event.reply_token, "你已經封鎖過了")
                return

            supabase.table("blacklist").insert({
                "user_id": user_id,
                "blocked_user_id": partner,
                "nickname": nickname
            }).execute()

            block_count = supabase.table("blacklist") \
                .select("*", count="exact") \
                .eq("blocked_user_id", partner) \
                .execute()

            if block_count.count >= 10:

                check_ban = supabase.table("banned_users") \
                    .select("*") \
                    .eq("user_id", partner) \
                    .execute()

                if not check_ban.data:

                    supabase.table("banned_users").insert({
                        "user_id": partner,
                        "reason": "被超過10人封鎖"
                    }).execute()

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", user_id) \
                .execute()

            supabase.table("chat_pairs") \
                .delete() \
                .eq("user_id", partner) \
                .execute()

            reply(event.reply_token, f"🚫 已封鎖 {nickname}")

            try:
                push_text(partner, "⚠️ 對方已離開聊天")
            except:
                pass

            return

        # =========================
        # 一般聊天
        # =========================
        result = get_partner(user_id)

        if result:

            partner = result["partner_id"]
            nickname = result["nickname"]

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

            reply(event.reply_token, "輸入「開始」開始匿名聊天")

    except Exception as e:
        print(e)


# =========================
# 貼圖
# =========================
@handler.add(MessageEvent, message=StickerMessageContent)
def handle_sticker(event):

    try:

        user_id = event.source.user_id

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

        result = get_partner(user_id)

        if not result:
            return

        partner = result["partner_id"]

        package_id = str(event.message.package_id)
        sticker_id = str(event.message.sticker_id)

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
        print(e)


# =========================
# 圖片
# =========================
@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):

    try:

        user_id = event.source.user_id

        result = get_partner(user_id)

        if not result:
            return

        partner = result["partner_id"]
        nickname = result["nickname"]

        content = get_content(event.message.id)

        filename = f"{uuid.uuid4()}.jpg"

        supabase.storage.from_("chat-images").upload(
            filename,
            content,
            {"content-type": "image/jpeg"}
        )

        image_url = supabase.storage \
            .from_("chat-images") \
            .get_public_url(filename)

        if isinstance(image_url, dict):
            image_url = image_url["publicUrl"]

        supabase.table("chat_logs").insert({
            "sender_id": user_id,
            "receiver_id": partner,
            "sender_name": nickname,
            "message_type": "image",
            "message": image_url
        }).execute()

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
        print(e)


# =========================
# 語音
# =========================
@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):

    try:

        user_id = event.source.user_id

        result = get_partner(user_id)

        if not result:
            return

        partner = result["partner_id"]

        content = get_content(event.message.id)

        filename = f"{uuid.uuid4()}.m4a"

        supabase.storage.from_("chat-images").upload(
            filename,
            content,
            {"content-type": "audio/m4a"}
        )

        audio_url = supabase.storage \
            .from_("chat-images") \
            .get_public_url(filename)

        if isinstance(audio_url, dict):
            audio_url = audio_url["publicUrl"]

        with ApiClient(configuration) as api_client:

            line_bot_api = MessagingApi(api_client)

            line_bot_api.push_message(
                PushMessageRequest(
                    to=partner,
                    messages=[
                        AudioMessage(
                            original_content_url=audio_url,
                            duration=5000
                        )
                    ]
                )
            )

    except Exception as e:
        print(e)


# =========================
# 影片
# =========================
@handler.add(MessageEvent, message=VideoMessageContent)
def handle_video(event):

    try:

        user_id = event.source.user_id

        result = get_partner(user_id)

        if not result:
            return

        partner = result["partner_id"]

        content = get_content(event.message.id)

        filename = f"{uuid.uuid4()}.mp4"

        supabase.storage.from_("chat-images").upload(
            filename,
            content,
            {"content-type": "video/mp4"}
        )

        video_url = supabase.storage \
            .from_("chat-images") \
            .get_public_url(filename)

        if isinstance(video_url, dict):
            video_url = video_url["publicUrl"]

        with ApiClient(configuration) as api_client:

            line_bot_api = MessagingApi(api_client)

            line_bot_api.push_message(
                PushMessageRequest(
                    to=partner,
                    messages=[
                        VideoMessage(
                            original_content_url=video_url,
                            preview_image_url=video_url
                        )
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
