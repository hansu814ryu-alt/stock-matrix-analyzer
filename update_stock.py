import FinanceDataReader as fdr
import pandas as pd
import datetime
import os

print("🚀 [1단계] 시가총액/거래량(Volume) 복합 스코어링 필터 가동...")

# 1. 오늘 기준 전 종목의 시가총액 및 거래량 데이터 가져오기
df_krx = fdr.StockListing('KRX')

# [중복 및 노이즈 제거] 우선주 및 코넥스 시장 종목 원천 배제
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

# 2. 각각 순위 매기기 (큰 값이 1등) - 거래대금이 아닌 순수 '거래량(Volume)' 사용
df_krx['시총순위'] = df_krx['Marcap'].rank(ascending=False)
df_krx['거래량순위'] = df_krx['Volume'].rank(ascending=False)

# 3. 50% + 50% 가중치 합산 후 최정예 500개 추출
df_krx['종합점수'] = (df_krx['시총순위'] * 0.5) + (df_krx['거래량순위'] * 0.5)
final_500 = df_krx.sort_values(by='종합점수').head(500)
target_codes = final_500['Code'].tolist()

print(f"🔥 순수 거래량 기준 주도주 {len(target_codes)}개 종목 선별 완료.")
print("📥 [2단계] 데이터 다이어트 및 증분 업데이트 시작...")

today_str = datetime.date.today().strftime('%Y-%m-%d')

# 4. 500개 종목을 돌면서 데이터 업데이트
for code in target_codes:
    file_name = f"data_{code}.csv"
    
    # 만약 기존 5년치 데이터 파일이 이미 깃허브에 있다면?
    if os.path.exists(file_name):
        # 오늘 하루치 데이터만 받아서 뒤에 붙이기 (증분 업데이트)
        df_existing = pd.read_csv(file_name, index_col=0)
        df_today = fdr.DataReader(code, start=today_str, end=today_str)
        
        if not df_today.empty:
            # 중복 방지를 위해 오늘 날짜가 없을 때만 결합
            if today_str not in df_existing.index:
                df_updated = pd.concat([df_existing, df_today])
                df_updated.to_csv(file_name)
    else:
        # 파일이 처음 생성되는 경우에만 과거 5개년치를 통째로 다운로드 (최초 1회만 실행됨)
        start_date = (datetime.date.today() - datetime.timedelta(days=5*365)).strftime('%Y-%m-%d')
        df_historical = fdr.DataReader(code, start=start_date, end=today_str)
        df_historical.to_csv(file_name)

print("📊 [3단계] 4×4 매트릭스 계산기 가동...")

# 5. 각 종목의 최신 상태를 분석하여 4×4 매트릭스 결과용 JSON 데이터 생성
matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}

for code in target_codes:
    file_name = f"data_{code}.csv"
    if not os.path.exists(file_name): continue
    
    df = pd.read_csv(file_name)
    if len(df) < 21: continue  # 최소 20일치 데이터가 있어야 평균 계산 가능
    
    # 최신 일봉 기준 상승률 및 거래량 비율 계산
    today_data = df.iloc[-1]
    prev_20_days = df.iloc[-21:-1]
    
    change_rate = ((today_data['Close'] - today_data['Open']) / today_data['Open']) * 100
    avg_volume = prev_20_days['Volume'].mean()
    vol_ratio = (today_data['Volume'] / avg_volume) * 100 if avg_volume > 0 else 0
    
    # 음봉이거나 주가 변동이 없으면 제외
    if change_rate <= 0: continue
    
    # 4×4 행렬 위치 선정 (상승률 축 / Y축)
    if change_rate < 3: row = 1
    elif change_rate < 6: row = 2
    elif change_rate < 12: row = 3
    else: row = 4
        
    # 4×4 행렬 위치 선정 (거래량 축 / X축)
    if vol_ratio < 100: col = 1
    elif vol_ratio < 200: col = 2
    elif vol_ratio < 500: col = 3
    else: col = 4
        
    # 종목명 찾기
    stock_name = final_500[final_500['Code'] == code]['Name'].values[0]
    
    # 해당 매트릭스 칸에 종목 정보 저장
    matrix_results[f"R{row}C{col}"].append({
        "code": code,
        "name": stock_name,
        "change": round(change_rate, 2),
        "volume": round(vol_ratio, 1)
    })

# 웹페이지가 읽어갈 수 있도록 최종 결과 파일 저장
with open('matrix_data.json', 'w', encoding='utf-8') as f:
    import json
    json.dump(matrix_results, f, ensure_ascii=False, indent=4)

print("🎉 순수 거래량 기반 4x4 매트릭스 연산이 완료되었습니다!")
