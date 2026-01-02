import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os
import requests
import twstock
import time  # <--- 新增這個，用來休息
from datetime import datetime

# --- 設定基本參數 ---
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

# 確保結果資料夾存在
if not os.path.exists('results'):
    os.makedirs('results')

print(f"[{datetime.now()}] 1. 正在取得全台股代碼清單...")

# 1. 取得股票代碼 (只抓上市)
stock_list = []
try:
    codes = twstock.codes
    for code in codes:
        row = codes[code]
        if row.type == '股票':
            if row.market == '上市':
                stock_list.append(code + '.TW')
            
    print(f"共取得 {len(stock_list)} 檔股票代碼。")
except Exception as e:
    print(f"取得代碼失敗: {e}")
    exit()

print(f"[{datetime.now()}] 2. 下載資料 (啟動防擋機制: 分批下載)...")

# --- 定義分批下載函數 ---
def download_in_chunks(tickers, chunk_size=50):
    all_dfs = []
    total_chunks = len(tickers) // chunk_size + 1
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i+chunk_size]
        current_chunk_idx = i // chunk_size + 1
        
        print(f"   -> 正在下載第 {current_chunk_idx}/{total_chunks} 批 (共 {len(chunk)} 檔)...")
        
        try:
            # 下載這批資料
            # threads=True 加速，但配合 chunk 使用比較安全
            batch_data = yf.download(chunk, period="2y", interval="1d", progress=False, threads=True)
            
            # 檢查是否有資料
            if not batch_data.empty:
                # 處理 yfinance 可能回傳的多層索引問題
                if 'Close' in batch_data.columns:
                    # 如果只有 Close 一層
                    if isinstance(batch_data['Close'], pd.DataFrame):
                         all_dfs.append(batch_data['Close'])
                    else:
                         # 單一股票可能回傳 Series，轉成 DataFrame
                         all_dfs.append(batch_data['Close'].to_frame())
                else:
                    # 舊版或特殊結構
                    all_dfs.append(batch_data)
            
        except Exception as e:
            print(f"   ⚠️ 第 {current_chunk_idx} 批下載失敗: {e}")
        
        # 關鍵：每批下載完休息 1.5 秒，避免被鎖 IP
        time.sleep(1.5)

    print("   -> 所有批次下載完成，正在合併資料...")
    if all_dfs:
        # 合併所有 DataFrame
        return pd.concat(all_dfs, axis=1)
    else:
        return pd.DataFrame()

# 2. 執行分批下載
try:
    # A. 下載個股資料
    df_close = download_in_chunks(stock_list, chunk_size=60) # 每次 60 檔
    
    # 過濾完全沒資料的空股票
    df_close = df_close.dropna(axis=1, how='all')
    print(f"有效個股數量: {df_close.shape[1]} 檔")
    
    # 檢查是否被鎖爛了 (如果數量太少)
    if df_close.shape[1] < 500:
        print("❌ 警告：有效股數過少，可能 IP 仍被 Yahoo 封鎖，請稍後再試。")
        # 這裡可以選擇不 exit，試著跑跑看，或者直接報錯

    # B. 下載大盤資料 (加權指數 ^TWII) - 單獨下載通常沒事
    print("   -> 下載大盤資料...")
    taiex_data = yf.download("^TWII", period="2y", interval="1d", progress=False)
    
    if 'Close' in taiex_data.columns:
        if isinstance(taiex_data.columns, pd.MultiIndex):
             taiex_close = taiex_data['Close']['^TWII'] 
        else:
             taiex_close = taiex_data['Close']
    else:
        taiex_close = taiex_data
    taiex_close = taiex_close.squeeze()
    
except Exception as e:
    print(f"下載流程發生嚴重錯誤: {e}")
    exit()

print(f"[{datetime.now()}] 3. 計算技術指標與多空比...")

# 3. 計算指標 (邏輯不變)
window = 200
rolling_max = df_close.rolling(window=window, min_periods=150).max()
rolling_min = df_close.rolling(window=window, min_periods=150).min()

is_new_high = (df_close >= rolling_max)
is_new_low = (df_close <= rolling_min)

market_breadth = pd.DataFrame()
market_breadth['New_Highs'] = is_new_high.sum(axis=1)
market_breadth['New_Lows'] = is_new_low.sum(axis=1)
market_breadth['TAIEX'] = taiex_close

plot_df = market_breadth.dropna().iloc[-120:].copy()

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
    cellText=table_display.values,
    colLabels=table_display.columns,
    rowLabels=table_display.index,
    loc='center', cellLoc='center', colWidths=[0.2, 0.2, 0.2]
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

ax_table.set_title(f"Market Breadth Data (Last 10 Days)", fontsize=14, pad=10)

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
        f'📊 **台股市場寬度日報**\n'
        f'📅 日期: {datetime.now().strftime("%Y-%m-%d")}\n'
        f'📈 200日新高: {int(today_stats["Highs"])} 家\n'
        f'📉 200日新低: {int(today_stats["Lows"])} 家\n'
        f'⚖️ 多空比: {int(today_stats["Ratio %"])}%\n'
        f'🔍 統計樣本: {df_close.shape[1]} 檔 (上市)\n'
        f'📝 包含最近10日數據表與大盤走勢對照'
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
