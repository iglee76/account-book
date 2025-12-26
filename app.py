import os
import json
from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

app = Flask(__name__)

# --- 1. 설정값 로딩 ---
def get_config():
    if os.environ.get("GOOGLE_CREDENTIALS"):
        creds_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
        sheet_url = os.environ.get("SHEET_URL")
        return creds_dict, sheet_url
    
    try:
        with open('secrets.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            sheet_url = data.get('spreadsheet_url')
            return data, sheet_url
    except FileNotFoundError:
        return None, None

def get_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds_dict, _ = get_config()
    if not creds_dict: return None
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

# --- 2. 메인 화면 ---
@app.route('/')
def home():
    try:
        client = get_client()
        _, sheet_url = get_config()
        doc = client.open_by_url(sheet_url)
        
        month_name = f"{datetime.now().month}월"
        try:
            ws = doc.worksheet(month_name)
        except:
            return render_template('index.html', income=0, expense=0, saving=0, invest=0)

        data = ws.get_all_values()
        
        income = expense = saving = invest = 0
        
        if len(data) > 3:
            for i, row in enumerate(data):
                if i < 3: continue 
                if len(row) > 7:
                    try:
                        val_str = str(row[7]).replace(',', '').replace('₩', '').replace(' ', '')
                        if not val_str or not val_str.replace('-','').isdigit(): continue
                        val = int(val_str)
                        
                        cat = row[3]
                        if cat == "수입": income += val
                        elif cat == "지출": expense += val
                        elif cat == "저축": saving += val
                        elif cat == "투자": invest += val
                    except:
                        continue
                        
        return render_template('index.html', 
                             income=f"{income:,}", 
                             expense=f"{expense:,}", 
                             saving=f"{saving:,}", 
                             invest=f"{invest:,}")
    except Exception as e:
        print(f"Error: {e}")
        return render_template('index.html', income=0, expense=0, saving=0, invest=0)

# --- 3. 데이터 저장 ---
@app.route('/submit', methods=['POST'])
def submit():
    try:
        data = request.json
        client = get_client()
        _, sheet_url = get_config()
        doc = client.open_by_url(sheet_url)
        
        date_obj = datetime.strptime(data['date'], '%Y-%m-%d')
        month_name = f"{date_obj.month}월"
        
        try:
            ws = doc.worksheet(month_name)
        except:
            return jsonify({"status": "error", "message": f"'{month_name}' 시트가 없습니다."})

        col_c = ws.col_values(3)
        last_row = len(col_c)
        next_row = last_row + 1
        if next_row < 21: next_row = 21

        updates = [
            {
                'range': f'C{next_row}:D{next_row}',
                'values': [[data['date'], data['mainCat']]]
            },
            {
                'range': f'G{next_row}:J{next_row}',
                'values': [[
                    data['detail'], 
                    int(data['amount']), 
                    data['payment'], 
                    data['desc']
                ]]
            }
        ]
        ws.batch_update(updates)

        return jsonify({"status": "success", "message": f"{month_name} 저장 완료! 🎉"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# --- [수정] 4. 통합 차트 데이터 API (차트변환용시트 사용) ---
@app.route('/api/yearly_stats/<category>')
def yearly_stats(category):
    try:
        client = get_client()
        _, sheet_url = get_config()
        doc = client.open_by_url(sheet_url)
        
        # "차트변환용시트" 열기
        try:
            ws = doc.worksheet("차트변환용시트")
        except gspread.WorksheetNotFound:
            return jsonify({"error": "'차트변환용시트'가 없습니다."})
            
        rows = ws.get_all_values()
        stats = {} 

        # AN열(39), AO열(40), BB열(53) 인덱스
        # 엑셀 열은 1부터 시작하지만, 파이썬 리스트는 0부터 시작하므로 -1 해줌
        IDX_MAIN = 39   # AN
        IDX_DETAIL = 40 # AO
        IDX_AMOUNT = 53 # BB

        for i, row in enumerate(rows):
            if i < 1: continue # 헤더가 있다면 스킵 (1행부터 데이터라면 0으로 수정)
            
            # BB열까지 데이터가 있는지 확인
            if len(row) > IDX_AMOUNT:
                row_cat = row[IDX_MAIN].strip()   # 대분류
                
                # 요청한 카테고리(수입, 지출 등)와 일치하는지 확인
                if row_cat == category:
                    detail = row[IDX_DETAIL].strip() # 상세내용
                    val_str = str(row[IDX_AMOUNT]).replace(',', '').replace('₩', '').replace(' ', '')
                    
                    if val_str and val_str.replace('-','').isdigit():
                        amount = int(val_str)
                        # 딕셔너리에 누적
                        if detail in stats:
                            stats[detail] += amount
                        else:
                            stats[detail] = amount

        return jsonify(stats)

    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == '__main__':
    app.run(debug=True)