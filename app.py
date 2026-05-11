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
# 貼圖 / 表情貼 冷卻時間
# =========================
sticker_cooldown = {}

# =========================
# Railway Variables
# =========================
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# =========================
# LINE
# =========================
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# =========================
# Supabase
# =========================
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


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
        # LINE Emoji 表情貼
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

                # 傳文字
                push_text(
                    partner,
                    f"{nickname}：{text}"
                )

                # 傳 emoji 圖
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

                        print("emoji錯誤")
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

            msg += "\n輸入：\n解除封鎖 編號"

            reply(event.reply_token, msg)

            return

        # =========================
        # 單獨解除封鎖
        # =========================
        if text.startswith("解除封鎖"):

            try:

                parts = text.split()

                if len(parts) < 2:

                    reply(event.reply_token, "格式：解除封鎖 編號")
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

                supabase.table("blacklist") \
                    .delete() \
                    .eq("id", target["id"]) \
                    .execute()

                reply(event.reply_token, "✅ 已解除封鎖")

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

            # 加入黑名單
            supabase.table("blacklist").insert({
                "user_id": user_id,
                "blocked_user_id": partner,
                "nickname": nickname
            }).execute()

            # 離開聊天室
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

            # 已在等待池
            check_waiting = supabase.table("waiting_users") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if check_waiting.data:

                reply(event.reply_token, "⏳ 你已經在等待配對中了")
                return

            # 已在聊天
            check_chat = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if check_chat.data:

                reply(event.reply_token, "💬 你目前已經在聊天中了")
                return

            # 找等待中的人
            waiting_users = supabase.table("waiting_users") \
                .select("*") \
                .neq("user_id", user_id) \
                .execute()

            partner = None

            for row in waiting_users.data:

                target = row["user_id"]

                # 我封鎖對方？
                check1 = supabase.table("blacklist") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .eq("blocked_user_id", target) \
                    .execute()

                # 對方封鎖我？
                check2 = supabase.table("blacklist") \
                    .select("*") \
                    .eq("user_id", target) \
                    .eq("blocked_user_id", user_id) \
                    .execute()

                if check1.data or check2.data:
                    continue

                partner = target
                break

            # 有人等待
            if partner:

                # 一小時內不重複配對
                one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

                recent = supabase.table("recent_pairs") \
                    .select("*") \
                    .or_(
                        f"and(user1.eq.{user_id},user2.eq.{partner}),"
                        f"and(user1.eq.{partner},user2.eq.{user_id})"
                    ) \
                    .gte("created_at", one_hour_ago.isoformat()) \
                    .execute()

                if recent.data:

                    supabase.table("waiting_users") \
                        .upsert({
                            "user_id": partner
                        }) \
                        .execute()

                    reply(
                        event.reply_token,
                        "⏳ 正在尋找新的聊天對象..."
                    )

                    return

                # 移除等待池
                supabase.table("waiting_users") \
                    .delete() \
                    .eq("user_id", partner) \
                    .execute()

                # 隨機暱稱
                nickname1 = generate_nickname()
                nickname2 = generate_nickname()

                # 建立聊天室
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

                # 記錄最近配對
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
                push_text(partner, "⚠️ 對方已離開聊天")
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

            push_text(
                partner,
                f"{nickname}：{text}"
            )

        else:

            reply(event.reply_token, "輸入「開始」開始匿名聊天")

    except Exception as e:

        print("文字錯誤")
        print(e)


# =========================
# LINE貼圖
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

                push_text(
                    user_id,
                    f"⏳ 你的手速太快了，請 {remain} 秒後再試"
                )

                return

        sticker_cooldown[user_id] = now

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

        try:

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

            return

        except Exception:
            pass

        urls = [

            f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/ANDROID/sticker.png",

            f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_animation.png",

            f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_popup.png",

            f"https://stickershop.line-scdn.net/sticonshop/v1/sticon/{sticker_id}/iPhone/001.png"
        ]

        sticker_url = None

        for url in urls:

            try:

                response = requests.get(url, timeout=10)

                if response.status_code == 200:

                    sticker_url = url
                    break

            except:
                pass

        if not sticker_url:

            push_text(partner, "🎭 對方傳送了一個特殊貼圖")
            return

        with ApiClient(configuration) as api_client:

            line_bot_api = MessagingApi(api_client)

            line_bot_api.push_message(
                PushMessageRequest(
                    to=partner,
                    messages=[
                        ImageMessage(
                            original_content_url=sticker_url,
                            preview_image_url=sticker_url
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

        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return

        filename = f"{uuid.uuid4()}.jpg"

        supabase.storage.from_("chat-images").upload(
            filename,
            response.content,
            {"content-type": "image/jpeg"}
        )

        image_url = supabase.storage.from_("chat-images").get_public_url(filename)

        if isinstance(image_url, dict):
            image_url = image_url["publicUrl"]

        push_text(partner, f"{nickname}：傳送了一張圖片")

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
# 語音
# =========================
@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):

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

        push_text(partner, f"🎤 {nickname} 傳送了一段語音")

    except Exception as e:

        print("語音錯誤")
        print(e)


# =========================
# 影片
# =========================
@handler.add(MessageEvent, message=VideoMessageContent)
def handle_video(event):

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

        push_text(partner, f"🎬 {nickname} 傳送了一段影片")

    except Exception as e:

        print("影片錯誤")
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

        print("reply錯誤")
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

        print("push錯誤")
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
