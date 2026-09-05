"""
금 시세 자동 반영 스크립트
=========================
매일 실행되어:
1. 공공데이터포털에서 오늘의 국내 금시세(원/g)를 가져오고
2. products.csv에 적어둔 상품별 중량/공임비/마진율로 판매가를 계산하고
3. 네이버 커머스 API로 각 상품의 판매가를 갱신합니다.

실행에 필요한 값 4가지는 모두 "환경변수"로 받습니다.
(코드에 직접 적지 않는 이유: GitHub에 올려도 키가 노출되지 않게 하기 위해서입니다)
  - NAVER_CLIENT_ID
  - NAVER_CLIENT_SECRET
  - GOLD_API_SERVICE_KEY   (공공데이터포털에서 받은 서비스키, Encoding된 값)
  - GOLD_API_ENDPOINT      (아래 get_gold_price_per_gram() 설명 참고, 필요시 사용)

GitHub Actions에서는 이 값들을 저장소의 "Secrets"에 등록해두면
워크플로우 실행 시 자동으로 환경변수로 들어옵니다. (뒤에서 안내)
"""

import os
import sys
import time
import csv
import base64
import bcrypt
import requests

# ---------------------------------------------------------------
# 0. 설정값 읽기
# ---------------------------------------------------------------
NAVER_CLIENT_ID = os.environ["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = os.environ["NAVER_CLIENT_SECRET"]
GOLD_API_SERVICE_KEY = os.environ["GOLD_API_SERVICE_KEY"]

PRODUCTS_CSV_PATH = os.path.join(os.path.dirname(__file__), "products.csv")


# ---------------------------------------------------------------
# 1. 금 시세 가져오기 (공공데이터포털 - 금융위원회 일반상품시세정보)
# ---------------------------------------------------------------
def get_gold_price_per_gram() -> int:
    """
    오늘(또는 가장 최근 영업일)의 국내 KRX 금시장 1g당 금시세(원)를 반환합니다.

    실제 응답 확인 결과:
    - itmsNm이 "금 99.99_1kg"인 항목의 clpr(종가) 값이 1g당 원화 가격입니다.
      (예: clpr=207500 -> 1g에 207,500원)
    - 결과는 최신 날짜(basDt)가 맨 앞에 옵니다.
    """
    GOLD_API_URL = "http://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo"

    params = {
        "serviceKey": GOLD_API_SERVICE_KEY,
        "resultType": "json",
        "numOfRows": "10",
        "pageNo": "1",
    }

    resp = requests.get(GOLD_API_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    result_code = data["response"]["header"]["resultCode"]
    if result_code != "00":
        raise RuntimeError(f"금시세 API 오류: {data['response']['header']['resultMsg']}")

    items = data["response"]["body"]["items"]["item"]
    if isinstance(items, dict):
        items = [items]

    # "금 99.99_1kg" 항목 중 가장 최근 날짜(basDt)의 clpr을 사용
    gold_items = [i for i in items if i["itmsNm"] == "금 99.99_1kg"]
    if not gold_items:
        raise RuntimeError("금 99.99_1kg 항목을 찾지 못했습니다. API 응답을 다시 확인해주세요.")
    gold_items.sort(key=lambda i: i["basDt"], reverse=True)
    latest = gold_items[0]

    price_per_gram_ex_vat = int(float(latest["clpr"]))
    price_per_gram_incl_vat = int(round(price_per_gram_ex_vat * 1.1))
    print(f"   (기준일: {latest['basDt']}, 종목: {latest['itmsNm']}, 부가세별도: {price_per_gram_ex_vat:,}원, 부가세포함: {price_per_gram_incl_vat:,}원)")
    return price_per_gram_incl_vat


# ---------------------------------------------------------------
# 2. 네이버 커머스 API 인증 (OAuth2 client_credentials + bcrypt 서명)
# ---------------------------------------------------------------
def get_naver_access_token() -> str:
    timestamp = str(int((time.time() - 3) * 1000))
    password = f"{NAVER_CLIENT_ID}_{timestamp}"
    hashed = bcrypt.hashpw(password.encode("utf-8"), NAVER_CLIENT_SECRET.encode("utf-8"))
    signature = base64.b64encode(hashed).decode("utf-8")

    url = "https://api.commerce.naver.com/external/v1/oauth2/token"
    data = {
        "client_id": NAVER_CLIENT_ID,
        "timestamp": timestamp,
        "client_secret_sign": signature,
        "grant_type": "client_credentials",
        "type": "SELF",
    }
    resp = requests.post(url, data=data, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    if "access_token" not in result:
        raise RuntimeError(f"네이버 토큰 발급 실패: {result}")
    return result["access_token"]


def get_channel_product(access_token: str, product_no: str) -> dict:
    url = f"https://api.commerce.naver.com/external/v2/products/channel-products/{product_no}"
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def update_channel_product_price(access_token: str, product_no: str, product_data: dict, new_price: int):
    """
    조회한 상품 정보(product_data)를 그대로 두고 salePrice만 바꿔서 다시 전송합니다.
    (네이버 API는 부분 수정이 아니라 전체 재전송 방식이라, 다른 필드를 건드리지 않도록 주의)
    """
    # ⚠️ 실제 응답 JSON 구조에 맞게 경로를 확인해주세요.
    # 보통 product_data["originProduct"]["salePrice"] 형태입니다.
    product_data["originProduct"]["salePrice"] = new_price

    url = f"https://api.commerce.naver.com/external/v2/products/channel-products/{product_no}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    resp = requests.put(url, headers=headers, json=product_data, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------
# 3. 상품 목록(csv) 읽고 가격 계산
# ---------------------------------------------------------------
def load_products():
    products = []
    with open(PRODUCTS_CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(row for row in f if not row.startswith("#"))
        for row in reader:
            products.append(row)
    return products


def calculate_price(product_type: str, weight_g: float, labor_fee: int, margin_rate: float, gold_price_per_gram_incl_vat: int) -> int:
    # 순금은 중량 그대로, 14K/18K는 순금 환산 중량(중량 x 0.64)으로 계산
    purity_factor = 1.0 if product_type.strip() == "순금" else 0.64
    pure_weight = weight_g * purity_factor
    base = pure_weight * gold_price_per_gram_incl_vat + labor_fee
    price = base * (1 + margin_rate)
    # 100원 단위 반올림
    return int(round(price / 100.0) * 100)


# ---------------------------------------------------------------
# 4. 메인 실행
# ---------------------------------------------------------------
def main():
    print("1) 오늘의 금시세 조회 중...")
    gold_price = get_gold_price_per_gram()
    print(f"   -> 1g당 {gold_price:,}원")

    print("2) 상품 목록 불러오는 중...")
    products = load_products()
    print(f"   -> {len(products)}개 상품")

    print("3) 네이버 커머스 API 로그인 중...")
    token = get_naver_access_token()

    success, failed = 0, 0
    for p in products:
        product_no = p["product_no"].strip()
        product_type = p["product_type"].strip()
        weight_g = float(p["weight_g"])
        labor_fee = int(p["labor_fee"])
        margin_rate = float(p["margin_rate"])

        new_price = calculate_price(product_type, weight_g, labor_fee, margin_rate, gold_price)

        try:
            product_data = get_channel_product(token, product_no)
            update_channel_product_price(token, product_no, product_data, new_price)
            print(f"   [성공] {product_no} ({p.get('product_name','')}) -> {new_price:,}원")
            success += 1
        except Exception as e:
            print(f"   [실패] {product_no} -> {e}")
            failed += 1

        time.sleep(0.6)  # 네이버 API 초당 호출 제한 대응

    print(f"\n완료: 성공 {success}건 / 실패 {failed}건")
    if failed > 0:
        sys.exit(1)  # GitHub Actions에서 실패로 표시되게 함


if __name__ == "__main__":
    main()
