from flask import Flask, request
import os
import requests
import uuid

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    ImageMessage
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

            result = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .limit(1) \
                .execute()

            if result.data:

                partner = result.data[0]["partner_id"]

                emoji = event.message.emojis[0]

                product_id = emoji.product_id
                emoji_id = emoji.emoji_id

                print("表情貼")
                print(product_id)
                print(emoji_id)

                emoji_url = (
                    f"https://stickershop.line-scdn.net/"
                    f"sticonshop/v1/sticon/{product_id}/iPhone/{emoji_id}.png"
                )

                print(emoji_url)

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

            return

        # =========================
        # 開始配對
        # =========================
        if text == "開始":

            print("開始配對")

            # 檢查是否已在等待池
            check_waiting = supabase.table("waiting_users") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if check_waiting.data:

                reply(event.reply_token, "⏳ 你已經在等待配對中了")
                return

            # 檢查是否已在聊天中
            check_chat = supabase.table("chat_pairs") \
                .select("*") \
                .eq("user_id", user_id) \
                .execute()

            if check_chat.data:

                reply(event.reply_token, "💬 你目前已經在聊天中了")
                return

            # 找等待中的人
            result = supabase.table("waiting_users") \
                .select("*") \
                .neq("user_id", user_id) \
                .limit(1) \
                .execute()

            print(result.data)

            # 有人等待
            if result.data:

                partner = result.data[0]["user_id"]

                # 從等待池移除對方
                supabase.table("waiting_users") \
                    .delete() \
                    .eq("user_id", partner) \
                    .execute()

                # 建立聊天室
                supabase.table("chat_pairs").insert([
                    {
                        "user_id": user_id,
                        "partner_id": partner
                    },
                    {
                        "user_id": partner,
                        "partner_id": user_id
                    }
                ]).execute()

                reply(event.reply_token, "✅ 配對成功！")
                push_text(partner, "✅ 配對成功！")

            # 沒人等待
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

            # 刪除雙方聊天室
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

            push_text(partner, text)

        else:

            reply(event.reply_token, "輸入「開始」開始匿名聊天")

    except Exception as e:

        print("文字錯誤")
        print(e)


# =========================
# LINE貼圖 → 圖片
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

        print("貼圖")
        print(package_id)
        print(sticker_id)

        # 多種貼圖網址
        urls = [

            # 一般貼圖
            f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/ANDROID/sticker.png",

            # 動態貼圖
            f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_animation.png",

            # Popup貼圖
            f"https://stickershop.line-scdn.net/stickershop/v1/sticker/{sticker_id}/IOS/sticker_popup.png",

            # Emoji表情貼
            f"https://stickershop.line-scdn.net/sticonshop/v1/sticon/{sticker_id}/iPhone/001.png"
        ]

        sticker_url = None

        # 找可用網址
        for url in urls:

            response = requests.get(url)

            print(url)
            print(response.status_code)

            if response.status_code == 200:

                sticker_url = url
                break

        # 全失敗
        if not sticker_url:

            push_text(partner, "🎭 對方傳送了一個特殊表情")
            return

        print("找到貼圖網址:")
        print(sticker_url)

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

        print("貼圖成功轉圖片")

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

        message_id = event.message.id

        print("圖片 message_id:")
        print(message_id)

        headers = {
            "Authorization": "Bearer " + CHANNEL_ACCESS_TOKEN
        }

        url = f"https://api-data.line.me/v2/bot/message/{message_id}/content"

        response = requests.get(url, headers=headers)

        print("status:")
        print(response.status_code)

        if response.status_code != 200:

            print("圖片下載失敗")
            print(response.text)
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

        print("圖片成功轉發")

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

        push_text(partner, "🎤 對方傳送了一段語音")

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

        push_text(partner, "🎬 對方傳送了一段影片")

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
