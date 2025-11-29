import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime

# --- 設定繪圖風格 (選用) ---
plt.style.use('ggplot')

# 1. 股票清單
stock_list = [
    '2330.TW', '2317.TW', '2454.TW', '2308.TW', '2303.TW', '2881.TW', '2882.TW', 
    '1301.TW', '1303.TW', '2002.TW', '1216.TW', '2886.TW', '2891.TW', '3008.TW',
    '3045.TW', '5880.TW', '2884.TW', '4938.TW', '2892.TW', '5871.TW', '2382.TW'
]

print(f"[{datetime.now()}] 開始執行自動化分析...")

# 2. 下載資料
try:
    data = yf.download(stock_list, period="2y", interval="1d", progress=False)
    if 'Close' in data.columns:
        df_close = data['Close']
    else:
        df_close = data
except Exception as e:
    print(f"下載失敗: {e}")
    exit()

# 3. 計算 200 日新高/新低
window = 200
rolling_max = df_close.rolling(window=window, min_periods=window).max()
rolling_min = df_close.rolling(window=window, min_periods=window).min()

is_new_high = (df_close >= rolling_max)
is_new_low = (df_close <= rolling_min)

market_breadth = pd.DataFrame()
market_breadth['New_Highs_Count'] = is_new_high.sum(axis=1)
market_breadth['New_Lows_Count'] = is_new_low.sum(axis=1)

# 只取最近 180 天
analysis_df = market_breadth.iloc[-180:]

# 4. 繪圖
plt.figure(figsize=(12, 6))
plt.plot(analysis_df.index, analysis_df['New_Highs_Count'], color='red', label='New Highs (200d)')
plt.plot(analysis_df.index, analysis_df['New_Lows_Count'], color='green', label='New Lows (200d)')
plt.fill_between(analysis_df.index, analysis_df['New_Highs_Count'], color='red', alpha=0.1)
plt.fill_between(analysis_df.index, analysis_df['New_Lows_Count'], color='green', alpha=0.1)

plt.title(f'TWSE Market Breadth - Updated: {datetime.now().date()}')
plt.ylabel('Count')
plt.legend()
plt.grid(True, alpha=0.3)
plt.gcf().autofmt_xdate()

# 5. 【關鍵修改】儲存結果而不是顯示
# 建立一個 results 資料夾 (如果不存在)
if not os.path.exists('results'):
    os.makedirs('results')

# 儲存圖片 (覆蓋舊圖，或加上日期也可)
plt.savefig('results/market_breadth.png')
print("圖片已儲存至 results/market_breadth.png")

# 儲存 CSV
analysis_df.tail().to_csv('results/latest_data.csv')
print("數據已儲存至 results/latest_data.csv")