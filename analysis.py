import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import os
import requests
import twstock
from datetime import datetime

# --- 設定繪圖風格與字型 ---
plt.style.use('ggplot')

# 確保結果資料夾存在
if not os.path.exists('results'):
    os.makedirs('results')

print(f"[{datetime.now()}] 1. 正在取得全台股代碼清單...")

# 自動取得全台股代碼 (上市 + 上櫃)
stock_list = []
try:
    codes = twstock.codes
    for code in codes:
        row = codes[code]
        if row.type == '股票':
            if row.market == '上市':
                stock_list.append(code + '.TW')
            elif row.market == '上櫃':
                stock_list.append(code + '.TWO')
    print(f"共取得 {len(stock_list)} 檔股票代碼。")
except Exception as e:
    print(f"取得代碼失敗: {e}")
    exit()

print(f"[{datetime.now()}] 2. 開始下載歷史資料 (改為 2 年數據)...")

# 下載資料
try:
    # 【修正 1】改用 2y (兩年)，確保扣掉假日後還有大於 200 筆資料
    # threads=True 開啟多執行緒加速
    data = yf.download(stock_list, period="2y", interval="1d", progress=False, threads=True)
    
    # 處理資料結構
    if 'Close' in data.columns:
        df_close = data['Close']
    else:
        df_close = data

    # 過濾掉「完全沒資料」的空股票 (例如已下市)
    df_close = df_close.dropna(axis=1, how='all')
    
    # 【偵錯重點】印出實際成功下載的數量
    print(f"📊 原始清單: {len(stock_list)} 檔 -> 實際有效資料: {df_close.shape[1]} 檔")
    
    if df_close.shape[1] < 100:
        print("⚠️ 警告：有效股票過少，可能是 yfinance 下載遭擋或格式改變。")

except Exception as e:
    print(f"下載失敗: {e}")
    exit()

print(f"[{datetime.now()}] 3. 計算 200 日新高與新低...")

window = 200

# 【修正 2】min_periods 改為 150
# 允許資料中間有缺漏 (颱風、停牌)，只要有 150 筆以上就計算，避免股票被誤刪
rolling_max = df_close.rolling(window=window, min_periods=150).max()
rolling_min = df_close.rolling(window=window, min_periods=150).min()

# 判斷新高新低
# 這裡加一個容許值 (>= 0.999) 避免浮點數誤差，但嚴格來說用 >= 即可
is_new_high = (df_close >= rolling_max)
is_new_low = (df_close <= rolling_min)

# 每日加總
market_breadth = pd.DataFrame()
market_breadth['New_Highs_Count'] = is_new_high.sum(axis=1)
market_breadth['New_Lows_Count'] = is_new_low.sum(axis=1)

# 取最近半年數據繪圖
analysis_df = market_breadth.iloc[-120:]

print(f"[{datetime.now()}] 4. 繪製圖表...")

plt.figure(figsize=(14, 7))

# 繪製區域圖
plt.fill_between(analysis_df.index, analysis_df['New_Highs_Count'], color='red', alpha=0.3)
plt.plot(analysis_df.index, analysis_df['New_Highs_Count'], color='red', linewidth=2, label='New Highs (200d)')

plt.fill_between(analysis_df.index, analysis_df['New_Lows_Count'], color='green', alpha=0.3)
plt.plot(analysis_df.index, analysis_df['New_Lows_Count'], color='green', linewidth=2, label='New Lows (200d)')

# 加上今天的數值標籤在圖上
last_date = analysis_df.index[-1].strftime('%Y-%m-%d')
last_high = int(analysis_df['New_Highs_Count'].iloc[-1])
last_low = int(analysis_df['New_Lows_Count'].iloc[-1])

plt.title(f'TWSE Market Breadth (Sample: {df_close.shape[1]} Stocks) - {last_date}')
plt.ylabel('Number of Stocks')
plt.legend(loc='upper left')
plt.grid(True, alpha=0.3)
plt.gcf().autofmt_xdate()

# 存檔
img_path = 'results/market_breadth.png'
plt.savefig(img_path)
print("圖表已儲存。")

# --- 傳送 Telegram 通知 ---
print(f"[{datetime.now()}] 5. 傳送 Telegram 通知...")

tg_token = os.environ.get('TELEGRAM_TOKEN')
chat_id = os.environ.get('TELEGRAM_CHAT_ID')

if tg_token and chat_id:
    url = f"https://api.telegram.org/bot{tg_token}/sendPhoto"
    
    caption = (
        f'📊 **台股全市場寬度分析**\n'
        f'📅 日期: {last_date}\n'
        f'🔍 統計樣本: {df_close.shape[1]} 檔\n'
        f'📈 創200日新高: {last_high} 家\n'
        f'📉 創200日新低: {last_low} 家\n'
        f'🤖 自動化報告'
    )
    
    try:
        with open(img_path, 'rb') as img_file:
            files = {'photo': img_file}
            data = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'Markdown'
            }
            r = requests.post(url, data=data, files=files)
            
        if r.status_code == 200:
            print("Telegram 通知發送成功！✅")
        else:
            print(f"Telegram 發送失敗: {r.text}")
    except Exception as e:
        print(f"發送過程發生錯誤: {e}")
else:
    print("⚠️ 未設定 Telegram Token，跳過通知。")
