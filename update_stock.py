import FinanceDataReader as fdr
import pandas as pd
import datetime
import os
import json
import time

print("🚀 [시스템 개정] 1주(5영업일) 기반 백테스팅 및 실전 패턴 추적 엔진 가동...")

# 1. 한국 시장 전체 보통주 라인업 로드
df_krx = fdr.StockListing('KRX')
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

target_codes = df_krx['Code'].tolist()
name_dict = dict(zip(df_krx['Code'], df_krx['Name']))

start_date = (datetime.date.today() - datetime.timedelta(days=5*365)).strftime('%Y-%m-%d')
today_str = datetime.date.today().strftime('%Y-%m-%d')

history_file = "matrix_history.csv"
if os.path.exists(history_file):
    df_history = pd.read_csv(history_file)
    df_history['Code'] = df_history['Code'].astype(str).str.zfill(6)
else:
    df_history = pd.DataFrame(columns=[
        'Date', 'Code', 'Name', 'Cell', 'Base_Price', 
        '1D_Return', '3D_Return', '5D_Return', 'Settled_Count'
    ])

matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []
ma_breakthrough_stocks = []
new_high_stocks = []

print(f"📥 [2단계] {len(target_codes)}개 종목 전수조사 및 신고가 판별 중...")

for code in target_codes:
    try:
        code_str = str(code).zfill(6)
        df = fdr.DataReader(code_str, start=start_date, end=today_str)
        if len(df) < 61: continue 
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        today_data = df.iloc[-1]
        prev_data = df.iloc[-2]
        today_close = today_data['Close']
        prev_close = prev_data['Close']
        prev_vol = prev_data['Volume']
        today_vol = today_data['Volume']
        
        if prev_close == 0 or prev_vol == 0: continue
        
        change_rate = ((today_close - prev_close) / prev_close) * 100
        vol_ratio = (today_vol / prev_vol) * 100
        stock_name = name_dict.get(code_str, code_str)

        if change_rate > 0:
            df_1yr = df.iloc[-252:] if len(df) >= 252 else df
            high_52w = df_1yr['High'].max()
            high_all = df['High'].max()
            if today_close >= high_all:
                new_high_stocks.append({"code": code_str, "name": stock_name, "type": "역사적 신고가"})
            elif today_close >= high_52w:
                new_high_stocks.append({"code": code_str, "name": stock_name, "type": "52주 신고가"})

        if change_rate <= 0: continue 
        
        break_ma5 = bool(prev_data['Close'] <= prev_data['MA5'] and today_close > today_data['MA5'])
        break_ma20 = bool(prev_data['Close'] <= prev_data['MA20'] and today_close > today_data['MA20'])
        break_ma60 = bool(prev_data['Close'] <= prev_data['MA60'] and today_close > today_data['MA60'])
        
        if break_ma5 or break_ma20 or break_ma60:
            ma_breakthrough_stocks.append({
                "code": code_str, "name": stock_name,
                "ma5": break_ma5, "ma20": break_ma20, "ma60": break_ma60
            })
            
        row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
        col = 1 if vol_ratio < 100 else 2 if vol_ratio < 150 else 3 if vol_ratio < 200 else 4
        cell_id = f"R{row}C{col}"
        
        past_records = df_history[df_history['Code'] == code_str] if not df_history.empty else pd.DataFrame()
        if not past_records.empty:
            first_date = str(past_records['Date'].min())
            first_cell = str(past_records[past_records['Date'] == first_date]['Cell'].values[0])
        else:
            first_date = today_str
            first_cell = cell_id
            
        matrix_results[cell_id].append({
            "code": code_str, "name": stock_name, "change": round(change_rate, 2), "volume": round(vol_ratio, 1),
            "first_date": first_date, "first_cell": first_cell
        })
        
        today_captured_list.append({
            'Date': today_str, 'Code': code_str, 'Name': stock_name, 'Cell': cell_id,
            'Base_Price': today_close, '1D_Return': None, '3D_Return': None, '5D_Return': None, 'Settled_Count': 0
        })
        
    except Exception as e:
        pass
    time.sleep(0.02)

print("📝 [3단계] 기본 장부 정산 중...")
df_unsettled = df_history[df_history['Settled_Count'] < 3]

for idx, row_data in df_unsettled.iterrows():
    code_str = str(row_data['Code']).zfill(6)
    try:
        df_stock = fdr.DataReader(code_str, start=row_data['Date'], end=today_str)
        passed_days = len(df_stock) - 1
        
        if passed_days >= 1 and pd.isna(df_history.loc[idx, '1D_Return']):
            df_history.loc[idx, '1D_Return'] = round(((df_stock.iloc[1]['Close'] - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
        if passed_days >= 3 and pd.isna(df_history.loc[idx, '3D_Return']):
            idx_3d = min(3, len(df_stock)-1)
            df_history.loc[idx, '3D_Return'] = round(((df_stock.iloc[idx_3d]['Close'] - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
        if passed_days >= 5 and pd.isna(df_history.loc[idx, '5D_Return']):
            idx_5d = min(5, len(df_stock)-1)
            df_history.loc[idx, '5D_Return'] = round(((df_stock.iloc[idx_5d]['Close'] - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
    except:
        pass

if today_captured_list:
    df_history = pd.concat([df_history, pd.DataFrame(today_captured_list)], ignore_index=True)
df_history.to_csv(history_file, index=False)

print("📊 [4단계] 퀀트 백테스팅 스캔...")
ranking_list = []
c4_stats_data = {
    'R2C4': {'total':0, 'a_suc':0, 'b_suc':0},
    'R3C4': {'total':0, 'a_suc':0, 'b_suc':0},
    'R4C4': {'total':0, 'a_suc':0, 'b_suc':0}
}

if not df_history.empty:
    c4_cells = ['R2C4', 'R3C4', 'R4C4']
    df_c4_history = df_history[df_history['Cell'].isin(c4_cells)].sort_values(by=['Code', 'Date'])
    
    for code, group in df_c4_history.groupby('Code'):
        count = len(group)
        if count >= 5:
            code_str = str(code).zfill(6)
            fifth_event = group.iloc[4]
            d_day = str(fifth_event['Date'])
            finale_cell = str(fifth_event['Cell'])
            base_price = float(fifth_event['Base_Price'])
            
            try:
                df_future = fdr.DataReader(code_str, start=d_day).iloc[1:6]
                if len(df_future) > 0:
                    c4_stats_data[finale_cell]['total'] += 1
                    max_high = df_future['High'].max()
                    last_close = df_future['Close'].iloc[-1]
                    
                    if max_high >= base_price * 1.2:
                        c4_stats_data[finale_cell]['a_suc'] += 1
                    if last_close >= base_price * 1.2:
                        c4_stats_data[finale_cell]['b_suc'] += 1
            except:
                pass
            
            first_date = str(group['Date'].min())
            cells_path = group['Cell'].tolist()
            ranking_list.append({
                "code": code_str, 
                "name": name_dict.get(code_str, code_str), 
                "count": int(count),
                "first_date": first_date,
                "history_cells": cells_path,
                "finale_cell": finale_cell
            })
    
    ranking_list = sorted(ranking_list, key=lambda x: x['count'], reverse=True)

c4_statistics = {}
for cell, s in c4_stats_data.items():
    tot = s['total']
    prob_a = round((s['a_suc'] / tot * 100), 1) if tot > 0 else 0.0
    prob_b = round((s['b_suc'] / tot * 100), 1) if tot > 0 else 0.0
    c4_statistics[cell] = {'prob_a': prob_a, 'prob_b': prob_b, 'total': tot}

print("🕵️ [5단계] 실전 패턴 검색용 최근 3일치 궤적(Path) 추출 중...")
# [신규 로직] 모든 종목의 최근 3일치 이동 경로를 추출하여 웹에 전달
recent_paths = {}
if not df_history.empty:
    df_sorted = df_history.sort_values(by=['Code', 'Date'])
    for code, group in df_sorted.groupby('Code'):
        code_str = str(code).zfill(6)
        path = group['Cell'].tail(3).tolist() # 최근 3개만 유지
        recent_paths[code_str] = {
            "name": name_dict.get(code_str, code_str),
            "path": path
        }

print("⚙️ [6단계] 웹 배포용 고밀도 단일 JSON 패키징 빌드...")
final_web_data = {
    "captured": matrix_results,         
    "rankings": ranking_list,           
    "ma_breakthroughs": ma_breakthrough_stocks,
    "new_highs": new_high_stocks,
    "c4_statistics": c4_statistics,
    "recent_paths": recent_paths  # 프론트엔드 패턴검색 및 즐겨찾기 추적용
}

with open('matrix_data.json', 'w', encoding='utf-8') as f:
    json.dump(final_web_data, f, ensure_ascii=False, indent=4)

print("🎉 개정 로직 배포 준비 완료!")
