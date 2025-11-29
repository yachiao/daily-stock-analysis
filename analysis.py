import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import os
import requests
import twstock
from datetime import datetime

# --- 設定基本參數 ---
# 為了在 GitHub Actions 避免中文亂碼，圖表使用英文介面，但內容是通用的
plt.style.use('ggplot')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.unicode_minus'] = False

# 確保結果資料夾存在
if not os.path.exists('results'):
    os.makedirs('results')

print(f"[{datetime.now()}] 1. 正在取得全台股代碼清單...")

# 1. 取得股票代碼
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

print(f"[{datetime.now()}] 2. 下載資料 (個股 + 大盤)...")

# 2. 下載資料
try:
    # A. 下載個股資料 (2年)
    data = yf.download(stock_list, period="2y", interval="1d", progress=False, threads=True)
    if 'Close' in data.columns:
        df_close = data['Close']
    else:
        df_close = data
    
    # 過濾空值
    df_close = df_close.dropna(axis=1, how='all')
    print(f"有效個股數量: {df_close.shape[1]} 檔")

    # B. 下載大盤資料 (加權指數 ^TWII)
    taiex_data = yf.download("^TWII", period="2y", interval="1d", progress=False)
    # yfinance 新版可能回傳 MultiIndex，確保只取 Close
    if 'Close' in taiex_data.columns:
        if isinstance(taiex_data.columns, pd.MultiIndex):
             taiex_close = taiex_data['Close']['^TWII'] # 針對新版結構
        else:
             taiex_close = taiex_data['Close']
    else:
        taiex_close = taiex_data
        
    # 確保是 Series 格式
    taiex_close = taiex_close.squeeze()
    
except Exception as e:
    print(f"下載失敗: {e}")
    exit()

print(f"[{datetime.now()}] 3. 計算技術指標與多空比...")

# 3. 計算指標
window = 200
# 寬鬆標準：200天內有150天資料即計算
rolling_max = df_close.rolling(window=window, min_periods=150).max()
rolling_min = df_close.rolling(window=window, min_periods=150).min()

# 判斷新高新低
is_new_high = (df_close >= rolling_max)
is_new_low = (df_close <= rolling_min)

# 每日加總
market_breadth = pd.DataFrame()
market_breadth['New_Highs'] = is_new_high.sum(axis=1)
market_breadth['New_Lows'] = is_new_low.sum(axis=1)

# 加入大盤指數 (對齊日期)
market_breadth['TAIEX'] = taiex_close

# 清除 NaN 並取最近半年 (120天) 用於畫圖
plot_df = market_breadth.dropna().iloc[-120:].copy()

# --- 製作表格數據 (取最近 10 天) ---
table_df = market_breadth.dropna().iloc[-10:].copy()
# 計算多空比 (High / Low) * 100%
# 避免除以 0 的錯誤，若 Low 為 0，則給一個很大的比例或顯示 N/A
table_df['Ratio'] = table_df.apply(
    lambda row: round((row['New_Highs'] / row['New_Lows']) * 100) if row['New_Lows'] > 0 else 999, axis=1
)
# 整理表格顯示格式
table_display = table_df[['New_Highs', 'New_Lows', 'Ratio']].sort_index(ascending=False) # 日期由新到舊
table_display.index = table_display.index.strftime('%m-%d') # 日期格式 MM-DD
table_display.columns = ['Highs', 'Lows', 'Ratio %'] # 英文欄位

print(f"[{datetime.now()}] 4. 繪製複合圖表 (圖表+表格)...")

# 4. 繪圖 (使用 GridSpec 進行版面配置)
fig = plt.figure(figsize=(12, 12)) # 拉長高度以容納表格
gs = GridSpec(2, 1, height_ratios=[1, 3]) # 上面 1 等份放表格，下面 3 等份放圖表

# --- 上半部：表格 (Table) ---
ax_table = fig.add_subplot(gs[0])
ax_table.axis('off') # 隱藏座標軸

# 繪製表格
the_table = ax_table.table(
    cellText=table_display.values,
    colLabels=table_display.columns,
    rowLabels=table_display.index,
    loc='center',
    cellLoc='center',
    colWidths=[0.2, 0.2, 0.2]
)
the_table.auto_set_font_size(False)
the_table.set_fontsize(12)
the_table.scale(1, 1.5) # 調整表格高度

# 針對 Ratio 欄位上色 (大於 100% 紅色，小於 20% 綠色)
for i in range(len(table_display)):
    ratio_val = table_display.iloc[i]['Ratio %']
    cell = the_table[i+1, 2] # (row, col) row從1開始因為0是標題
    if ratio_val >= 100:
        cell.get_text().set_color('red')
        cell.get_text().set_weight('bold')
    elif ratio_val <= 20:
        cell.get_text().set_color('green')

ax_table.set_title(f"Market Breadth Data (Last 10 Days)", fontsize=14, pad=10)

# --- 下半部：走勢圖 (Chart) ---
ax_chart = fig.add_subplot(gs[1])

# 雙軸設定
ax_index = ax_chart.twinx() # 右軸：加權指數

# 繪製右軸：加權指數 (灰色線條，當背景看)
ax_index.plot(plot_df.index, plot_df['TAIEX'], color='gray', alpha=0.5, linewidth=1.5, linestyle='--', label='TAIEX Index')
ax_index.set_ylabel('TAIEX Index', color='gray')

# 繪製左軸：新高新低 (實心區域)
ax_chart.fill_between(plot_df.index, plot_df['New_Highs'], color='red', alpha=0.3)
ax_chart.plot(plot_df.index, plot_df['New_Highs'], color='red', linewidth=2, label='New Highs (200d)')

ax_chart.fill_between(plot_df.index, plot_df['New_Lows'], color='green', alpha=0.3)
ax_chart.plot(plot_df.index, plot_df['New_Lows'], color='green', linewidth=2, label='New Lows (200d)')

ax_chart.set_ylabel('Number of Stocks')
ax_chart.set_title('Market Breadth vs TAIEX Index', fontsize=14)
ax_chart.legend(loc='upper left')
ax_chart.grid(True, alpha=0.3)

# 調整日期顯示
fig.autofmt_xdate()

# 存檔
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
    
    # 準備今日數據
    today_stats = table_display.iloc[0] # 最上面一筆是最新日期
    caption = (
        f'📊 **台股市場寬度日報**\n'
        f'📅 日期: {datetime.now().strftime("%Y-%m-%d")}\n'
        f'📈 200日新高: {int(today_stats["Highs"])} 家\n'
        f'📉 200日新低: {int(today_stats["Lows"])} 家\n'
        f'⚖️ 多空比: {int(today_stats["Ratio %"])}%\n'
        f'📝 包含最近10日數據表與大盤走勢對照'
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
