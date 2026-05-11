from flask import Flask, request
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, ReplyMessageRequest, PushMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.exceptions import InvalidSignatureError

app = Flask(__name__)

# 換成你的 LINE 資料
CHANNEL_ACCESS_TOKEN = 'KMdUe6vh6Plm8L+wjd8shdNiVm2qRcuZa3D3xjDXzKxlxlO46lxEUJUcahNua92k2iQKQUoiGgNkQSMgbqJ873 eXeeS2RCF9dOnlUVVWyC04iJCkt4H/kPwkWkOacuK6wqPj06wd2LHTfd0QsahyewdB04t89/1O/w1cDnyilFU='
CHANNEL_SECRET = '2d9b5104560c31a0237d69238a520188'

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

waiting_users = []
pairs = {}

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return 'Invalid signature', 400

    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):

    user_id = event.source.user_id
    text = event.message.text.strip()

    if text == "開始":

        if waiting_users:

            partner = waiting_users.pop(0)

            pairs[user_id] = partner
            pairs[partner] = user_id

            reply(event.reply_token, "配對成功！")
            push(partner, "配對成功！")

        else:

            waiting_users.append(user_id)
            reply(event.reply_token, "等待配對中...")

        return

    if text == "離開":

        if user_id in pairs:

            partner = pairs[user_id]

            del pairs[user_id]
            del pairs[partner]

            push(partner, "對方已離開聊天")
            reply(event.reply_token, "你已離開聊天")

        else:
            reply(event.reply_token, "目前沒有聊天對象")

        return

    if user_id in pairs:

        partner = pairs[user_id]
        push(partner, text)

    else:
        reply(event.reply_token, "輸入「開始」開始匿名聊天")


def reply(reply_token, text):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=text)]
            )
        )


def push(user_id, text):
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        line_bot_api.push_message(
            PushMessageRequest(
                to=user_id,
                messages=[TextMessage(text=text)]
            )
        )


if __name__ == "__main__":
    app.run(port=5000)
