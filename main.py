import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# -----------------------------------------------------------
# 1. 한국 시간(KST) 기준으로 날짜 설정하기
# -----------------------------------------------------------
# 배포된 서버의 시간이 다를 수 있으므로 한국 시간(UTC+9)으로 고정합니다.
KST = timezone(timedelta(hours=9))
today_kst = datetime.now(KST).date()
yesterday_kst = today_kst - timedelta(days=1)


# -----------------------------------------------------------
# 2. 화면 구성 및 날짜 선택기(달력) 추가
# -----------------------------------------------------------
st.set_page_config(page_title="일간 박스오피스", page_icon="🍿")
st.title(f"🍿 일간 박스오피스")

# 달력 위젯 생성: 기본값은 어제, 고를 수 있는 가장 늦은 날짜(max_value)도 어제로 제한
selected_date = st.date_input(
    "조회할 날짜를 선택하세요", 
    value=yesterday_kst, 
    max_value=yesterday_kst
)

# 선택된 날짜를 API가 요구하는 'YYYYMMDD' 형식으로 변환합니다.
target_dt = selected_date.strftime('%Y%m%d')


# -----------------------------------------------------------
# 3. 데이터 가져오기 (캐싱 적용)
# -----------------------------------------------------------
# 같은 날짜를 선택하면 다시 API를 부르지 않도록 1시간(3600초) 동안 기억합니다.
@st.cache_data(ttl=3600)
def fetch_box_office_data(date_str, api_key):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": date_str
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() 
        return response.json()      
    except Exception as e:
        return {"network_error": str(e)}

# secrets에서 인증키 불러오기
if "KOBIS_KEY" not in st.secrets:
    st.error("🚨 스트림릿 설정(Secrets)에 `KOBIS_KEY`가 없습니다. 인증키 설정을 확인해 주세요.")
    st.stop()

api_key = st.secrets["KOBIS_KEY"]

with st.spinner("데이터를 불러오는 중입니다..."):
    data = fetch_box_office_data(target_dt, api_key)


# -----------------------------------------------------------
# 4. 에러 및 예외 상황 처리하기
# -----------------------------------------------------------
if "network_error" in data:
    st.error("📡 인터넷 연결이나 영화진흥위원회 서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")
    st.stop()

if "faultInfo" in data:
    error_msg = data["faultInfo"].get("message", "알 수 없는 오류")
    st.error(f"🔑 API 인증키 문제로 데이터를 가져오지 못했습니다.\n\n확인 내용: {error_msg}")
    st.stop()

if "boxOfficeResult" not in data or "dailyBoxOfficeList" not in data["boxOfficeResult"]:
    st.error("📉 영화진흥위원회에서 예상치 못한 형태의 데이터를 보냈습니다. 잠시 후 다시 확인해 주세요.")
    st.stop()

movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]

# 고른 날짜에 데이터가 아직 비어있을 경우 안내 문구 출력
if len(movie_list) == 0:
    st.warning("🎬 그날은 아직 집계 전입니다.")
    st.stop()


# -----------------------------------------------------------
# 5. 데이터 가공하기 (숫자 변환, 화살표/트로피 추가)
# -----------------------------------------------------------
df = pd.DataFrame(movie_list)

# 문자열로 온 숫자들을 정렬과 계산을 위해 진짜 정수형(int)으로 변환
df['rank'] = df['rank'].astype(int)
df['rankInten'] = df['rankInten'].astype(int)
df['audiCnt'] = df['audiCnt'].astype(int)
df['audiAcc'] = df['audiAcc'].astype(int)
df['scrnCnt'] = df['scrnCnt'].astype(int)

# 순위 증감 화살표 적용 함수
def format_rank_inten(val):
    if val > 0:
        return f"🔺 {val}" # 양수면 빨간 위 화살표
    elif val < 0:
        return f"🔽 {abs(val)}" # 음수면 파란(기본) 아래 화살표와 절대값
    else:
        return "-" # 변동 없으면 줄표

df['순위 증감'] = df['rankInten'].apply(format_rank_inten)

# 누적관객 100만 돌파 트로피 적용 함수
def format_movie_name(row):
    name = row['movieNm']
    if row['audiAcc'] >= 1000000:
        name += " 🏆"
    return name

df['영화명'] = df.apply(format_movie_name, axis=1)


# -----------------------------------------------------------
# 6. 화면에 예쁘게 보여주기
# -----------------------------------------------------------
st.divider() 

# --- [1위 영화 지표 카드] ---
top1_movie = df.iloc[0] 
st.subheader(f"🥇 1위: {top1_movie['영화명']}")

col1, col2, col3 = st.columns(3)
col1.metric(label="일일 관객수", value=f"{top1_movie['audiCnt']:,}명")
col2.metric(label="누적 관객수", value=f"{top1_movie['audiAcc']:,}명")
col3.metric(label="스크린 수", value=f"{top1_movie['scrnCnt']:,}개")

st.divider()

# --- [상위 5편 막대그래프] ---
st.subheader("📊 관객수 상위 5편")
# 상위 5개 자른 후, '영화명'(트로피 포함)을 기준으로 'audiCnt'(관객수)를 그래프로 출력
top5_df = df.head(5)[['영화명', 'audiCnt']].set_index('영화명')
st.bar_chart(top5_df, y_label="관객수 (명)")

st.divider()

# --- [전체 순위 표] ---
st.subheader("📋 박스오피스 전체 순위")
# 보여줄 컬럼 선택 및 이름 한글화 (순위 증감 컬럼 추가)
display_df = df[['rank', '순위 증감', '영화명', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
display_df.columns = ['순위', '순위 증감', '영화명', '개봉일', '관객수', '누적관객수', '스크린수']

# 데이터프레임을 화면에 출력
st.dataframe(display_df, hide_index=True, use_container_width=True)
