import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os
import requests
import twstock
import time
from datetime import datetime, timedelta
from FinMind.data import DataLoader
from tqdm import tqdm

# --- 設定基本參數 ---
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

# 確保結果資料夾存在
if not os.path.exists('results'):
    os.makedirs('results')

print(f"[{datetime.now()}] 1. 正在取得全台股代碼清單 (上市)...")

stock_list = []
try:
    codes = twstock.codes
    for code in codes:
        row = codes[code]
        if row.type == '股票':
            if row.market == '上市':
                stock_list.append(code)
            
    print(f"共取得 {len(stock_list)} 檔上市股票代碼。")
except Exception as e:
    print(f"取得代碼失敗: {e}")
    exit()

print(f"[{datetime.now()}] 2. 啟動 FinMind 馬拉松下載 (預計耗時 30 分鐘)...")

# --- 定義 FinMind 下載函數 (馬拉松版) ---
def download_finmind_marathon(tickers, lookback_days=400):
    dl = DataLoader()
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    all_data = []
    
    # 設定批次大小與休息時間
    # FinMind 免費版限制每小時約 600 次
    # 我們設定每批 200 檔，休息 300 秒 (5分鐘)，確保不撞牆
    BATCH_SIZE = 200
    SLEEP_SECONDS = 300 
    
    total_tickers = len(tickers)
    
    # 批次處理
    for i in range(0, total_tickers, BATCH_SIZE):
        batch = tickers[i : i + BATCH_SIZE]
        batch_idx = (i // BATCH_SIZE) + 1
        total_batches = (total_tickers // BATCH_SIZE) + 1
        
        print(f"\n🚀 正在執行第 {batch_idx}/{total_batches} 批次 (本批 {len(batch)} 檔)...")
        
        # 下載該批次
        for ticker in tqdm(batch, desc=f"Batch {batch_idx}"):
            try:
                df = dl.taiwan_stock_daily(stock_id=ticker, start_date=start_date)
                if not df.empty:
                    df = df[['date', 'stock_id', 'close']]
                    all_data.append(df)
            except Exception as e:
                pass
        
        # 如果不是最後一批，就強制休息
        if i + BATCH_SIZE < total_tickers:
            print(f"😴 為了避開 API 限制，強制休息 {SLEEP_SECONDS/60} 分鐘...請稍候...")
            time.sleep(SLEEP_SECONDS)
            print("⏰ 休息結束，繼續工作！")

    if not all_data:
        return pd.DataFrame()
        
    print(f"\n✅ 所有資料下載完成！正在合併 {len(all_data)} 檔數據...")
    
    big_df = pd.concat(all_data)
    # 移除重複值 (保險起見)
    big_df = big_df.drop_duplicates()
    
    # 轉置表格
    df_pivot = big_df.pivot(index='date', columns='stock_id', values='close')
    df_pivot.index = pd.to_datetime(df_pivot.index)
    
    return df_pivot

# 2. 執行下載
try:
    # A. 下載個股 (執行馬拉松)
    df_close = download_finmind_marathon(stock_list, lookback_days=400)
    
    # 過濾空值
    df_close = df_close.dropna(axis=1, how='all')
    print(f"📊 有效個股數量: {df_close.shape[1]} 檔")
    
    # 如果數量太少 (小於 800)，代表還是有問題
    if df_close.shape[1] < 500:
        print("⚠️ 警告：下載數量仍偏少，可能是網路不穩或 API 異常。")
    
    # B. 下載大盤資料
    print("   -> 下載大盤資料...")
    try:
        dl = DataLoader()
        start_date = (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')
        taiex_df = dl.taiwan_stock_daily(stock_id='TAIEX', start_date=start_date)
        
        if not taiex_df.empty:
            taiex_df['date'] = pd.to_datetime(taiex_df['date'])
            taiex_close = taiex_df.set_index('date')['close']
        else:
            taiex_close = pd.Series(dtype=float)
            
    except Exception as e:
        print(f"大盤下載失敗: {e}")
        taiex_close = pd.Series(dtype=float)

except Exception as e:
    print(f"下載流程發生錯誤: {e}")
    exit()

print(f"[{datetime.now()}] 3. 計算技術指標與多空比...")

# 3. 計算指標
window = 200
df_close = df_close.ffill()

rolling_max = df_close.rolling(window=window, min_periods=150).max()
rolling_min = df_close.rolling(window=window, min_periods=150).min()

is_new_high = (df_close >= rolling_max)
is_new_low = (df_close <= rolling_min)

market_breadth = pd.DataFrame()
market_breadth['New_Highs'] = is_new_high.sum(axis=1)
market_breadth['New_Lows'] = is_new_low.sum(axis=1)

if not taiex_close.empty:
    market_breadth['TAIEX'] = taiex_close.reindex(market_breadth.index)
else:
    market_breadth['TAIEX'] = None

plot_df = market_breadth.dropna(subset=['New_Highs', 'New_Lows']).iloc[-120:].copy()

if plot_df.empty:
    print("❌ 錯誤：數據不足，無法繪圖。")
    exit()

# --- 製作表格 ---
table_df = market_breadth.dropna(subset=['New_Highs', 'New_Lows']).iloc[-10:].copy()
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

ax_table.set_title(f"Market Breadth (Full Market Scan)", fontsize=14, pad=10)

# 下半部：圖表
ax_chart = fig.add_subplot(gs[1])

if not plot_df['TAIEX'].isnull().all():
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
        f'📊 **台股市場寬度日報 (完整掃描版)**\n'
        f'📅 日期: {datetime.now().strftime("%Y-%m-%d")}\n'
        f'📈 新高: {int(today_stats["Highs"])} / 📉 新低: {int(today_stats["Lows"])}\n'
        f'⚖️ 多空比: {int(today_stats["Ratio %"])}%\n'
        f'🔍 有效樣本: {df_close.shape[1]} 檔\n'
        f'⏳ 耗時: 約30分鐘 (為確保完整性)'
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
