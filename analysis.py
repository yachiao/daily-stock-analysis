import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import os
import requests
import twstock
from datetime import datetime

# --- 設定中文字型 (選用，避免亂碼，若無則使用英文) ---
plt.rcParams['font.sans-serif'] = ['Microsoft JhengHei', 'Arial', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

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

print(f"[{datetime.now()}] 2. 開始下載歷史資料 (可能需要 3~5 分鐘)...")

# 下載資料
try:
    # 使用 1 年資料 (1y) 以節省記憶體並加快速度
    data = yf.download(stock_list, period="1y", interval="1d", progress=False)
    
    # 處理資料結構 (yfinance 新舊版相容)
    if 'Close' in data.columns:
        df_close = data['Close']
    else:
        df_close = data

    # 過濾掉完全沒資料的空股票
    df_close = df_close.dropna(axis=1, how='all')
    print(f"成功下載並保留 {df_close.shape[1]} 檔有效股票資料")

except Exception as e:
    print(f"下載失敗: {e}")
    exit()

print(f"[{datetime.now()}] 3. 計算 200 日新高與新低...")

window = 200
# 計算滾動最大與最小 (min_periods確保資料不足也能計算部分)
rolling_max = df_close.rolling(window=window, min_periods=window).max()
rolling_min = df_close.rolling(window=window, min_periods=window).min()

# 判斷新高新低 (當日收盤價 >= 過去200天最大值)
is_new_high = (df_close >= rolling_max)
is_new_low = (df_close <= rolling_min)

# 每日加總
market_breadth = pd.DataFrame()
market_breadth['New_Highs_Count'] = is_new_high.sum(axis=1)
market_breadth['New_Lows_Count'] = is_new_low.sum(axis=1)

# 取最近半年數據繪圖 (120個交易日)
analysis_df = market_breadth.iloc[-120:]

print(f"[{datetime.now()}] 4. 繪製圖表...")

plt.style.use('ggplot') # 使用好看的風格
plt.figure(figsize=(14, 7))

# 繪製區域圖 (Area Plot)
plt.fill_between(analysis_df.index, analysis_df['New_Highs_Count'], color='red', alpha=0.3)
plt.plot(analysis_df.index, analysis_df['New_Highs_Count'], color='red', linewidth=2, label='New Highs (200d)')

plt.fill_between(analysis_df.index, analysis_df['New_Lows_Count'], color='green', alpha=0.3)
plt.plot(analysis_df.index, analysis_df['New_Lows_Count'], color='green', linewidth=2, label='New Lows (200d)')

plt.title(f'TWSE Market Breadth (All Stocks) - Updated: {datetime.now().date()}')
plt.ylabel('Number of Stocks')
plt.legend(loc='upper left')
plt.grid(True, alpha=0.3)
plt.gcf().autofmt_xdate() # 自動旋轉日期標籤

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
    
    # 準備文字訊息
    high_count = int(analysis_df["New_Highs_Count"].iloc[-1])
    low_count = int(analysis_df["New_Lows_Count"].iloc[-1])
    
    caption = (
        f'📊 **台股全市場寬度分析**\n'
        f'📅 日期: {datetime.now().date()}\n'
        f'📈 創200日新高家數: {high_count}\n'
        f'📉 創200日新低家數: {low_count}\n'
        f'🤖 自動化分析報告'
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
