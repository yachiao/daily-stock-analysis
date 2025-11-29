import matplotlib.pyplot as plt
import pandas as pd
import os
import requests
from datetime import datetime

# 1. 建立結果資料夾
if not os.path.exists('results'):
    os.makedirs('results')

print("=== 開始 Telegram 連線測試 ===")

# 2. 製作一張測試用的假圖 (不抓股票)
print("正在繪製測試圖表...")
data = {'Day': [1, 2, 3, 4, 5], 'Value': [10, 50, 20, 80, 40]}
df = pd.DataFrame(data)

plt.figure(figsize=(10, 5))
plt.plot(df['Day'], df['Value'], marker='o', color='blue', label='Test Data')
plt.title(f'Telegram Connection Test - {datetime.now().date()}')
plt.legend()
plt.grid(True)

# 存檔
img_path = 'results/test_chart.png'
plt.savefig(img_path)
print(f"測試圖表已儲存至 {img_path}")

# 3. 測試發送 Telegram
print("準備發送訊息...")

# 從 GitHub Secrets 讀取密碼
tg_token = os.environ.get('TELEGRAM_TOKEN')
chat_id = os.environ.get('TELEGRAM_CHAT_ID')

# 檢查是否有讀到密碼
if not tg_token:
    print("❌ 錯誤: 未讀取到 TELEGRAM_TOKEN，請檢查 GitHub Secrets 設定。")
    exit()
if not chat_id:
    print("❌ 錯誤: 未讀取到 TELEGRAM_CHAT_ID，請檢查 GitHub Secrets 設定。")
    exit()

# 設定發送網址
url = f"https://api.telegram.org/bot{tg_token}/sendPhoto"

caption = (
    f"🚀 **Telegram 連線測試成功！**\n"
    f"📅 時間: {datetime.now()}\n"
    f"✅ 機器人運作正常，可以準備更新成全台股版本囉！"
)

try:
    with open(img_path, 'rb') as img_file:
        files = {'photo': img_file}
        data = {
            'chat_id': chat_id,
            'caption': caption,
            'parse_mode': 'Markdown'
        }
        # 發送請求
        response = requests.post(url, data=data, files=files)
        
    if response.status_code == 200:
        print("✅ Telegram 發送成功！請檢查你的手機。")
    else:
        print(f"❌ 發送失敗，錯誤代碼: {response.status_code}")
        print(f"錯誤訊息: {response.text}")

except Exception as e:
    print(f"❌ 程式執行發生錯誤: {e}")
