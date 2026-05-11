from flask import Flask, request
import os

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage
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

    return 'OK'


# =========================
# 文字訊息
# =========================
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text(event):

    user_id = event.source.user_id
    text = event.message.text.strip()

    # =========================
    # 開始配對
    # =========================
    if text == "開始":

        # 找等待中的人
        result = supabase.table("waiting_users") \
            .select("*") \
            .neq("user_id", user_id) \
            .limit(1) \
            .execute()

        # 有人等待
        if result.data:

            partner = result.data[0]["user_id"]

            # 從等待池移除
            supabase.table("waiting_users") \
                .delete() \
                .eq("user_id", partner) \
                .execute()

            # 建立聊天室配對
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
            .execute()

        if not result.data:

            reply(event.reply_token, "目前沒有聊天對象")
            return

        partner = result.data[0]["partner_id"]

        # 刪除雙方配對
        supabase.table("chat_pairs") \
            .delete() \
            .eq("user_id", user_id) \
            .execute()

        supabase.table("chat_pairs") \
            .delete() \
            .eq("user_id", partner) \
            .execute()

        push_text(partner, "對方已離開聊天")
        reply(event.reply_token, "你已離開聊天")

        return

    # =========================
    # 一般聊天訊息
    # =========================
    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if result.data:

        partner = result.data[0]["partner_id"]

        push_text(partner, text)

    else:

        reply(event.reply_token, "輸入「開始」開始匿名聊天")


# =========================
# LINE貼圖
# =========================
@handler.add(MessageEvent, message=StickerMessageContent)
def handle_sticker(event):

    user_id = event.source.user_id

    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if not result.data:
        return

    partner = result.data[0]["partner_id"]

    with ApiClient(configuration) as api_client:

        line_bot_api = MessagingApi(api_client)

        line_bot_api.push_message(
            PushMessageRequest(
                to=partner,
                messages=[
                    {
                        "type": "sticker",
                        "packageId": event.message.package_id,
                        "stickerId": event.message.sticker_id
                    }
                ]
            )
        )


# =========================
# 圖片
# =========================
@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image(event):

    user_id = event.source.user_id

    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if not result.data:
        return

    partner = result.data[0]["partner_id"]

    push_text(partner, "📷 對方傳送了一張圖片")


# =========================
# 語音
# =========================
@handler.add(MessageEvent, message=AudioMessageContent)
def handle_audio(event):

    user_id = event.source.user_id

    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if not result.data:
        return

    partner = result.data[0]["partner_id"]

    push_text(partner, "🎤 對方傳送了一段語音")


# =========================
# 影片
# =========================
@handler.add(MessageEvent, message=VideoMessageContent)
def handle_video(event):

    user_id = event.source.user_id

    result = supabase.table("chat_pairs") \
        .select("*") \
        .eq("user_id", user_id) \
        .execute()

    if not result.data:
        return

    partner = result.data[0]["partner_id"]

    push_text(partner, "🎬 對方傳送了一段影片")


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


if __name__ == "__main__":

    app.run(host="0.0.0.0", port=5000)
