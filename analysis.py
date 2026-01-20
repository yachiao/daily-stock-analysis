import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os
import requests
import twstock
import time
from datetime import datetime, timedelta
from FinMind.data import DataLoader

# --- 設定基本參數 ---
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

# 確保結果資料夾存在
if not os.path.exists('results'):
    os.makedirs('results')

print(f"[{datetime.now()}] 1. 正在取得全台股代碼清單 (上市)...")

# 1. 取得股票代碼 (只抓上市)
stock_list = []
try:
    codes = twstock.codes
    for code in codes:
        row = codes[code]
        if row.type == '股票':
            if row.market == '上市':
                stock_list.append(code) # FinMind 不需要 .TW
            
    print(f"共取得 {len(stock_list)} 檔上市股票代碼。")
except Exception as e:
    print(f"取得代碼失敗: {e}")
    exit()

print(f"[{datetime.now()}] 2. 啟動 FinMind 下載 (速度較慢請耐心等待)...")

# --- 定義 FinMind 下載函數 ---
def download_finmind_data(tickers, lookback_days=400):
    dl = DataLoader()
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    
    all_data = []
    total = len(tickers)
    
    print(f"   -> 準備下載區間: {start_date} ~ Now")
    
    # FinMind 下載迴圈
    for i, ticker in enumerate(tickers):
        try:
            # 下載個股資料
            df = dl.taiwan_stock_daily(stock_id=ticker, start_date=start_date)
            
            if not df.empty:
                # 只保留需要的欄位以節省記憶體
                df = df[['date', 'stock_id', 'close']]
                all_data.append(df)
            
        except Exception as e:
            pass # 個別失敗不影響整體
            
        # 顯示進度 (每 50 檔顯示一次，避免 Log 太多)
        if (i + 1) % 50 == 0:
            print(f"      已處理 {i + 1}/{total} 檔...")
            
    if not all_data:
        return pd.DataFrame()
        
    print("   -> 資料下載完成，正在整理格式 (Pivot)...")
    
    # 1. 合併所有資料
    big_df = pd.concat(all_data)
    
    # 2. 轉換格式: 長表轉寬表 (Index=Date, Columns=StockID, Values=Close)
    # 這是為了配合原本的計算邏輯
    df_pivot = big_df.pivot(index='date', columns='stock_id', values='close')
    
    # 3. 確保索引是時間格式
    df_pivot.index = pd.to_datetime(df_pivot.index)
    
    return df_pivot

# 2. 執行下載
try:
    # A. 下載個股
    # 為了計算 200MA，至少抓 400 天比較保險
    df_close = download_finmind_data(stock_list, lookback_days=400)
    
    # 過濾空值
    df_close = df_close.dropna(axis=1, how='all')
    print(f"有效個股數量: {df_close.shape[1]} 檔")
    
    if df_close.shape[1] < 100:
        print("❌ 錯誤：FinMind 下載數量過少，可能是 API 連線問題。")
        exit()

    # B. 下載大盤資料 (FinMind 大盤代碼是 TAIEX)
    print("   -> 下載大盤資料...")
    dl = DataLoader()
    start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
    
    taiex_df = dl.taiwan_stock_daily(stock_id='TAIEX', start_date=start_date)
    taiex_df['date'] = pd.to_datetime(taiex_df['date'])
    taiex_close = taiex_df.set_index('date')['close']

except Exception as e:
    print(f"下載流程發生錯誤: {e}")
    exit()

print(f"[{datetime.now()}] 3. 計算技術指標與多空比...")

# 3. 計算指標 (邏輯不變)
window = 200
# 填補空值 (FinMind 偶爾會有缺漏，用前一日收盤補齊)
df_close = df_close.ffill()

rolling_max = df_close.rolling(window=window, min_periods=150).max()
rolling_min = df_close.rolling(window=window, min_periods=150).min()

is_new_high = (df_close >= rolling_max)
is_new_low = (df_close <= rolling_min)

market_breadth = pd.DataFrame()
market_breadth['New_Highs'] = is_new_high.sum(axis=1)
market_breadth['New_Lows'] = is_new_low.sum(axis=1)
# 對齊大盤日期
market_breadth['TAIEX'] = taiex_close.reindex(market_breadth.index)

# 清除 NaN 並取最近半年
plot_df = market_breadth.dropna().iloc[-120:].copy()

if plot_df.empty:
    print("❌ 錯誤：數據計算後為空，無法繪圖。")
    exit()

# --- 製作表格 ---
table_df = market_breadth.dropna().iloc[-10:].copy()
table_df['Ratio'] = table_df.apply(
    lambda row: round((row['New_Highs'] / row['New_Lows']) * 100) if row['New_Lows'] > 0 else 999, axis=1
)
table_display = table_df[['New_Highs', 'New_Lows', 'Ratio']].sort_index(ascending=False)
table_display.index = table_display.index.strftime('%m-%d')
table_display.columns = ['Highs', 'Lows', 'Ratio %']

print(f"[{datetime.now()}] 4. 繪製複合圖表...")

# 4. 繪圖
fig = plt.figure(figsize=(12, 12))
gs = GridSpec(2, 1, height_ratios=[1, 3])

# 上半部：表格
ax_table = fig.add_subplot(gs[0])
ax_table.axis('off')
the_table = ax_table.table(
    cellText=table_display.values, colLabels=table_display.columns,
    rowLabels=table_display.index, loc='center', cellLoc='center', colWidths=[0.2, 0.2, 0.2]
)
the_table.auto_set_font_size(False)
the_table.set_fontsize(12)
the_table.scale(1, 1.5)

for i in range(len(table_display)):
    ratio_val = table_display.iloc[i]['Ratio %']
    cell = the_table[i+1, 2]
    if ratio_val >= 100:
        cell.get_text().set_color('red')
        cell.get_text().set_weight('bold')
    elif ratio_val <= 20:
        cell.get_text().set_color('green')

ax_table.set_title(f"Market Breadth (FinMind Source)", fontsize=14, pad=10)

# 下半部：圖表
ax_chart = fig.add_subplot(gs[1])
ax_index = ax_chart.twinx()

ax_index.plot(plot_df.index, plot_df['TAIEX'], color='gray', alpha=0.5, linewidth=1.5, linestyle='--', label='TAIEX Index')
ax_index.set_ylabel('TAIEX Index', color='gray')

ax_chart.fill_between(plot_df.index, plot_df['New_Highs'], color='red', alpha=0.3)
ax_chart.plot(plot_df.index, plot_df['New_Highs'], color='red', linewidth=2, label='New Highs (200d)')

ax_chart.fill_between(plot_df.index, plot_df['New_Lows'], color='green', alpha=0.3)
ax_chart.plot(plot_df.index, plot_df['New_Lows'], color='green', linewidth=2, label='New Lows (200d)')

ax_chart.set_ylabel('Number of Stocks')
ax_chart.set_title('Market Breadth vs TAIEX Index', fontsize=14)
ax_chart.legend(loc='upper left')
ax_chart.grid(True, alpha=0.3)
fig.autofmt_xdate()

img_path = 'results/market_report.png'
plt.tight_layout()
plt.savefig(img_path)
print("報表已儲存。")

# --- 5. 傳送 Telegram ---
print(f"[{datetime.now()}] 5. 傳送 Telegram 通知...")

tg_token = os.environ.get('TELEGRAM_TOKEN')
chat_id = os.environ.get('TELEGRAM_CHAT_ID')

if tg_token and chat_id:
    url = f"https://api.telegram.org/bot{tg_token}/sendPhoto"
    
    today_stats = table_display.iloc[0]
    caption = (
        f'📊 **台股市場寬度 (FinMind版)**\n'
        f'📅 日期: {datetime.now().strftime("%Y-%m-%d")}\n'
        f'📈 200日新高: {int(today_stats["Highs"])} 家\n'
        f'📉 200日新低: {int(today_stats["Lows"])} 家\n'
        f'⚖️ 多空比: {int(today_stats["Ratio %"])}%\n'
        f'🔍 統計樣本: {df_close.shape[1]} 檔 (上市)\n'
        f'📝 資料來源: FinMind (開源數據)'
    )
    
    try:
        with open(img_path, 'rb') as img_file:
            files = {'photo': img_file}
            data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
            r = requests.post(url, data=data, files=files)
            
        if r.status_code == 200:
            print("Telegram 通知發送成功！✅")
        else:
            print(f"Telegram 發送失敗: {r.text}")
    except Exception as e:
        print(f"發送過程發生錯誤: {e}")
else:
    print("⚠️ 未設定 Telegram Token，跳過通知。")
