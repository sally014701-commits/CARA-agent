"""
Generate the CARA backend synthetic dataset.

Outputs:
  - products.json
  - consumers.json

Python: 3.11+
Dependency: numpy
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


RANDOM_SEED = 42
PRODUCT_COUNT = 20000
CONSUMER_COUNT = 200

PSYCHOGRAPHIC_TYPES = ["maximizer", "value_seeker", "loss_averse", "impulsive", "hedonic", "utilitarian"]
PSYCHOGRAPHIC_COUNTS = [34, 34, 33, 33, 33, 33]
STYLE_TYPES = ("utilitarian", "hedonic")

CATEGORY_MAP = {
    "electronics": "전자기기",
    "fashion": "패션",
    "home_living": "홈/리빙",
    "beauty": "뷰티/퍼스널케어",
    "sports_outdoors": "스포츠/아웃도어",
    "food_grocery": "식품",
    "baby_kids": "유아/키즈",
    "books_media": "도서/미디어",
    "automotive": "자동차용품",
    "pet_supplies": "반려동물용품",
}

SUBCATEGORY_MAP = {
    "smartphones": "스마트폰",
    "laptops": "노트북",
    "earphones": "무선이어폰",
    "tablets": "태블릿",
    "smartwatches": "스마트워치",
    "cameras": "카메라",
    "monitors": "모니터",
    "keyboards": "키보드",
    "mice": "마우스",
    "chargers": "충전기",
    
    "mens_apparel": "남성의류",
    "womens_apparel": "여성의류",
    "footwear": "신발",
    "bags": "가방",
    "accessories": "악세사리",
    "watches": "시계",
    "hats": "모자",
    "scarves": "스카프",
    "belts": "벨트",
    
    "furniture": "가구",
    "lighting": "조명",
    "kitchenware": "주방용품",
    "bedding": "침구류",
    "storage": "수납용품",
    "cleaning_supplies": "청소용품",
    "candles": "캔들/방향제",
    "rugs": "러그/매트",
    
    "skincare": "스킨케어",
    "haircare": "헤어케어",
    "fragrance": "향수",
    "mens_grooming": "남성그루밍",
    "body_care": "바디케어",
    "makeup": "메이크업",
    "nail_care": "네일케어",
    
    "fitness_equipment": "운동기구",
    "outdoor_gear": "아웃도어장비",
    "cycling": "자전거용품",
    "swimming": "수영용품",
    "yoga_pilates": "요가/필라테스",
    "hiking": "등산용품",
    "team_sports": "구기스포츠",
    
    "health_foods": "건강식품",
    "beverages": "음료/차",
    "snacks": "간식/과자",
    "fresh_produce": "신선식품",
    "condiments": "조미료/소스",
    "supplements": "영양제",
    
    "infant_products": "영유아용품",
    "toys": "완구/장난감",
    "childrens_apparel": "아동의류",
    "school_supplies": "학용품",
    "baby_care": "베이비케어",
    
    "books": "도서",
    "music": "음반/음악",
    "film": "영화/블루레이",
    "games": "게임/콘솔",
    "stationery": "문구류",
    
    "car_accessories": "차량용액세서리",
    "car_care": "차량관리용품",
    "dash_cameras": "블랙박스",
    "car_electronics": "차량용전자기기",
    
    "dog_supplies": "강아지용품",
    "cat_supplies": "고양이용품",
    "pet_food": "반려동물사료",
    "treats": "반려동물간식",
    "pet_accessories": "반려동물액세서리",
    "pet_grooming": "반려동물미용",
}

CATEGORY_ITEMS = {
    "electronics":     ["smartphones", "laptops", "earphones", "tablets",
                        "smartwatches", "cameras", "monitors", "keyboards",
                        "mice", "chargers"],
    "fashion":         ["mens_apparel", "womens_apparel", "footwear", "bags",
                        "accessories", "watches", "hats", "scarves", "belts"],
    "home_living":     ["furniture", "lighting", "kitchenware", "bedding",
                        "storage", "cleaning_supplies", "candles", "rugs"],
    "beauty":          ["skincare", "haircare", "fragrance", "mens_grooming",
                        "body_care", "makeup", "nail_care"],
    "sports_outdoors": ["fitness_equipment", "outdoor_gear", "cycling",
                        "swimming", "yoga_pilates", "hiking", "team_sports"],
    "food_grocery":    ["health_foods", "beverages", "snacks",
                        "fresh_produce", "condiments", "supplements"],
    "baby_kids":       ["infant_products", "toys", "childrens_apparel",
                        "school_supplies", "baby_care"],
    "books_media":     ["books", "music", "film", "games", "stationery"],
    "automotive":      ["car_accessories", "car_care", "dash_cameras",
                        "car_electronics"],
    "pet_supplies":    ["dog_supplies", "cat_supplies", "pet_food",
                        "treats", "pet_accessories", "pet_grooming"],
}

CATEGORY_PRICE_RANGES = {
    "electronics":     (30_000,  1_500_000),
    "fashion":         (10_000,    500_000),
    "home_living":     (5_000,     800_000),
    "beauty":          (5_000,     200_000),
    "sports_outdoors": (10_000,    600_000),
    "food_grocery":    (1_000,      80_000),
    "baby_kids":       (5_000,     300_000),
    "books_media":     (3_000,     100_000),
    "automotive":      (5_000,     500_000),
    "pet_supplies":    (3_000,     150_000),
}

PSYCHOGRAPHIC_SESSION_PARAMS = {
    "maximizer":    {"page_visits_range": (25, 40), "dwell_range": (60, 200), "scroll_range": (0.7, 1.0), "ctr_base": 0.35, "query_ref_range": (3, 8)},
    "value_seeker": {"page_visits_range": (10, 25), "dwell_range": (30, 120), "scroll_range": (0.4, 0.8), "ctr_base": 0.50, "query_ref_range": (2, 6)},
    "loss_averse":  {"page_visits_range": (15, 35), "dwell_range": (45, 150), "scroll_range": (0.5, 0.9), "ctr_base": 0.40, "query_ref_range": (2, 7)},
    "impulsive":    {"page_visits_range": (3,  12), "dwell_range": (10, 60), "scroll_range": (0.2, 0.6), "ctr_base": 0.70, "query_ref_range": (0, 3)},
    "hedonic":      {"page_visits_range": (20, 35), "dwell_range": (60, 180), "scroll_range": (0.6, 1.0), "ctr_base": 0.45, "query_ref_range": (2, 6)},
    "utilitarian":  {"page_visits_range": (5,  18), "dwell_range": (20, 90), "scroll_range": (0.3, 0.7), "ctr_base": 0.55, "query_ref_range": (0, 3)},
}

TRANSLATIONS = {
    # Brand tiers
    "프리미엄": "Premium", "하이엔드": "High-End", "보급형": "Budget", "실속형": "Essential", "프로": "Pro",
    "디자이너": "Designer", "클래식": "Classic", "베이직": "Basic", "자연주의": "Naturalist", "웰빙": "Well-being",
    "에센셜": "Essential", "디자인가구": "Design Furniture", "모던라이프": "Modern Life",
    "스포티": "Sporty", "프로페셔널": "Professional", "엔트리": "Entry", "액티브": "Active", "하이포퍼먼스": "High Performance",
    "프레시": "Fresh", "유기농": "Organic", "세이프티": "Safety", "에코": "Eco", "키즈월드": "Kids World",
    "스탠다드": "Standard", "리미티드": "Limited", "스페셜 에디션": "Special Edition", "프로카": "Pro Car",
    "세이프": "Safe", "마스터": "Master", "에코펫": "Eco Pet", "해피테일": "Happy Tail", "내추럴": "Natural",

    # Style tags
    "미니멀": "Minimalist", "모던": "Modern", "감성": "Emotional", "심플": "Simple", "유니크": "Unique",
    "북유럽": "Scandinavian", "큐트": "Cute", "비비드": "Vivid", "레트로": "Retro", "블랙": "Black",

    # Use cases
    "대학생용": "College Student", "게이밍": "Gaming", "크리에이터용": "Creator", "사무용": "Office",
    "휴대용": "Portable", "전문가용": "Professional", "비즈니스용": "Business", "가정용": "Home",
    "데일리용": "Daily Use", "오피스룩": "Office Look", "캐주얼": "Casual", "여행용": "Travel",
    "피크닉용": "Picnic", "스트릿룩": "Street Look", "포멀": "Formal", "침실용": "Bedroom",
    "서재용": "Study Room", "주방용": "Kitchen", "거실용": "Living Room", "인테리어용": "Interior",
    "원룸용": "Studio Apartment", "민감성용": "Sensitive Skin", "건성용": "Dry Skin", "지성용": "Oily Skin",
    "데일리": "Daily", "선물용": "Gift", "집중케어용": "Intense Care", "홈트용": "Home Workout",
    "야외활동용": "Outdoor", "피트니스용": "Fitness", "필라테스용": "Pilates", "캠핑용": "Camping",
    "러닝용": "Running", "다이어트용": "Diet", "아침대용": "Breakfast", "간식용": "Snack",
    "건강식": "Health Food", "반찬용": "Side Dish", "신생아용": "Newborn", "유아동용": "Toddler",
    "놀이용": "Play", "등교용": "School", "출산선물용": "Baby Shower Gift", "목욕용": "Bath",
    "취미용": "Hobby", "학습용": "Study", "힐링용": "Healing", "콜렉터용": "Collector",
    "어린이용": "Kids", "세차용": "Car Wash", "차량 내부용": "Car Interior", "안전 운전용": "Safe Drive",
    "캠핑/차박용": "Car Camping", "자가정비용": "Self Maintenance", "노령견용": "Senior Dog",
    "신생묘용": "Kitten", "훈련용": "Training", "보양식": "Nourishing Food", "장거리 이동용": "Long Distance Travel",

    # Feature profiles
    "초경량": "Ultralight", "고성능": "High-Performance", "대용량": "Large Capacity", "스마트": "Smart",
    "가성비": "Cost-Effective", "슬림형": "Slim", "고해상도": "High Resolution", "저소음": "Low Noise",
    "속도 빠른": "Fast Speed", "경량": "Lightweight", "통기성 좋은": "Breathable", "편안한": "Comfortable",
    "트렌디한": "Trendy", "고급스러운": "Luxurious", "실용적인": "Practical",
    "친환경": "Eco-Friendly", "방수": "Waterproof", "수납이 편리한": "Easy Storage", "튼튼한": "Durable",
    "다용도": "Multi-Purpose", "공간절약형": "Space-Saving", "저자극": "Hypoallergenic", "수분충전": "Moisturizing",
    "진정효과": "Soothing", "미백": "Whitening", "주름개선": "Anti-Aging", "비건": "Vegan",
    "올인원": "All-in-One", "고탄성": "High Elasticity", "인체공학적": "Ergonomic", "충격흡수": "Shock Absorption",
    "미끄럼방지": "Anti-Slip", "내구성 좋은": "Durable", "무설탕": "Sugar-Free", "저칼로리": "Low Calorie",
    "고단백": "High Protein", "신선한": "Fresh", "천연성분": "Natural Ingredients",
    "간편한": "Convenient", "안전검증 완료": "Safety Certified", "부드러운": "Soft", "창의력 발달": "Creativity Developing",
    "베스트셀러": "Best Seller", "평점 높은": "Highly Rated", "소장가치 있는": "Collectible", "일러스트 포함": "Illustrated",
    "개정판": "Revised Edition", "고화질": "High Definition", "간편설치": "Easy Installation", "발수코팅": "Water Repellent",
    "저알레르기": "Hypoallergenic", "천연소재": "Natural Material", "스트레스 완화": "Stress Relief", "무독성": "Non-Toxic",

    # Product types
    "노트북": "Laptop", "울트라북": "Ultrabook", "태블릿 PC": "Tablet PC", "워크스테이션": "Workstation", "랩탑": "Laptop",
    "스마트폰": "Smartphone", "휴대폰": "Mobile Phone", "스마트 기기": "Smart Device", "무선 이어폰": "Wireless Earphones",
    "블루투스 이어폰": "Bluetooth Earphones", "헤드폰": "Headphones", "이어버드": "Earbuds", "태블릿": "Tablet",
    "패드": "Pad", "드로잉 태블릿": "Drawing Tablet", "스마트워치": "Smartwatch", "웨어러블 밴드": "Wearable Band",
    "피트니스 트래커": "Fitness Tracker", "미러리스 카메라": "Mirrorless Camera", "DSLR": "DSLR Camera", "액션캠": "Action Cam",
    "브이로그 카메라": "Vlog Camera", "게이밍 모니터": "Gaming Monitor", "와이드 모니터": "Wide Monitor", "4K 모니터": "4K Monitor",
    "사무용 모니터": "Office Monitor", "기계식 키보드": "Mechanical Keyboard", "무소음 키보드": "Silent Keyboard",
    "블루투스 키보드": "Bluetooth Keyboard", "무선 마우스": "Wireless Mouse", "버티컬 마우스": "Vertical Mouse",
    "게이밍 마우스": "Gaming Mouse", "고속 충전기": "Fast Charger", "멀티 어댑터": "Multi Adapter", "무선 충전 패드": "Wireless Charging Pad",
    "셔츠": "Shirt", "슬랙스": "Slacks", "자켓": "Jacket", "청바지": "Jeans", "맨투맨": "Sweatshirt",
    "니트": "Knitwear", "원피스": "Dress", "블라우스": "Blouse", "스커트": "Skirt", "가디건": "Cardigan",
    "스니커즈": "Sneakers", "로퍼": "Loafers", "구두": "Dress Shoes", "샌들": "Sandals", "런닝화": "Running Shoes",
    "운동화": "Athletic Shoes", "백팩": "Backpack", "숄더백": "Shoulder Bag", "크로스백": "Crossbody Bag", "토트백": "Tote Bag",
    "메신저백": "Messenger Bag", "목걸이": "Necklace", "귀걸이": "Earrings", "팔찌": "Bracelet", "반지": "Ring",
    "키링": "Keyring", "가죽 시계": "Leather Watch", "메탈 시계": "Metal Watch", "드레스 워치": "Dress Watch",
    "볼캡": "Ball Cap", "버킷햇": "Bucket Hat", "비니": "Beanie", "캡모자": "Cap", "머플러": "Muffler",
    "스카프": "Scarf", "쁘띠스카프": "Petit Scarf", "가죽 벨트": "Leather Belt", "캐주얼 벨트": "Casual Belt",
    "자동 벨트": "Automatic Belt", "책상": "Desk", "의자": "Chair", "수납장": "Cabinet",
    "소파": "Sofa", "침대 프레임": "Bed Frame", "식탁": "Dining Table", "무드등": "Mood Light",
    "단스탠드": "Table Lamp", "장스탠드": "Floor Lamp", "벽등": "Wall Light", "데스크 스탠드": "Desk Lamp",
    "냄비": "Pot", "프라이팬": "Frying Pan", "식기 세트": "Dinnerware Set", "칼블럭": "Knife Block",
    "머그잔": "Mug", "토퍼": "Topper", "이불 커버": "Duvet Cover", "베개 세트": "Pillow Set",
    "차렵 이불": "Comforter", "리빙박스": "Storage Box", "정리함": "Organizer", "옷걸이 행거": "Hanger Rack",
    "서랍장": "Chest of Drawers", "밀대 청소기": "Flat Mop", "청소용 브러쉬": "Cleaning Brush", "휴지통": "Trash Can",
    "물걸레": "Mop", "디퓨저": "Diffuser", "소이 캔들": "Soy Candle", "아로마 캔들": "Aroma Candle",
    "캔들 워머": "Candle Warmer", "단색 러그": "Solid Color Rug", "발매트": "Bath Mat", "사이잘룩 러그": "Sisal-look Rug",
    "거실 매트": "Living Room Mat", "토너": "Toner", "세럼": "Serum", "크림": "Cream",
    "에센스": "Essence", "마스크팩": "Mask Pack", "앰플": "Ampoule", "클렌저": "Cleanser",
    "샴푸": "Shampoo", "트리트먼트": "Treatment", "헤어에센스": "Hair Essence", "헤어팩": "Hair Pack",
    "오드퍼퓸": "Eau de Parfum", "드레스퍼퓸": "Dress Perfume", "향수": "Perfume", "보디미스트": "Body Mist",
    "올인원로션": "All-in-One Lotion", "쉐이빙폼": "Shaving Foam", "왁스": "Hair Wax", "폼클렌징": "Foam Cleanser",
    "바디로션": "Body Lotion", "바디워시": "Body Wash", "바디오일": "Body Oil", "핸드크림": "Hand Cream",
    "쿠션": "Cushion Foundation", "립밤": "Lip Balm", "아이섀도우": "Eyeshadow", "파운데이션": "Foundation",
    "틴트": "Lip Tint", "네일팁": "Nail Tips", "네일세럼": "Nail Serum", "젤네일": "Gel Nails",
    "덤벨": "Dumbbells", "요가매트": "Yoga Mat", "폼롤러": "Foam Roller", "실내자전거": "Spin Bike",
    "악력기": "Hand Gripper", "푸쉬업바": "Push Up Bar", "캠핑 체어": "Camping Chair", "텐트": "Tent",
    "타프": "Tarp", "랜턴": "Lantern", "등산스틱": "Trekking Poles", "헬멧": "Helmet",
    "자전거 라이트": "Bike Light", "안장 가방": "Saddle Bag", "사이클 장갑": "Cycling Gloves", "물안경": "Goggles",
    "수영모": "Swim Cap", "귀마개": "Earplugs", "수영가방": "Swim Bag", "요가 링": "Yoga Ring",
    "요가 삭스": "Yoga Socks", "필라테스 루프 밴드": "Pilates Loop Band", "등산화": "Hiking Boots", "등산 배낭": "Hiking Backpack",
    "무릎 보호대": "Knee Support", "축구공": "Soccer Ball", "농구공": "Basketball", "배드민턴 라켓": "Badminton Racket",
    "셔틀콕": "Shuttlecock", "닭가슴살": "Chicken Breast", "샐러드": "Salad", "오트밀": "Oatmeal",
    "곤약밥": "Konjac Rice", "드립백 커피": "Drip Bag Coffee", "유기농 녹차": "Organic Green Tea", "탄산수": "Sparkling Water",
    "콤부차": "Kombucha", "두유": "Soy Milk", "단백질 바": "Protein Bar", "통밀 크래커": "Whole Wheat Cracker",
    "아몬드": "Almonds", "건조 과일칩": "Dried Fruit Chips", "방울토마토": "Cherry Tomatoes", "사과": "Apple",
    "고구마": "Sweet Potato", "미니단호박": "Mini Sweet Pumpkin", "올리브유": "Olive Oil", "저칼로리 드레싱": "Low Calorie Dressing",
    "스테비아": "Stevia", "히말라야 핑크솔트": "Himalayan Pink Salt", "유산균": "Probiotics", "오메가3": "Omega-3",
    "멀티비타민": "Multivitamin", "루테인": "Lutein", "젖병 소독기": "Baby Bottle Sterilizer", "아기 침대": "Baby Crib",
    "유모차 라이너": "Stroller Liner", "보행기": "Baby Walker", "원목 블록": "Wooden Blocks", "오감 발달 촉감책": "Sensory Touch Book",
    "조립식 완구": "Building Toy", "역할놀이 세트": "Role Play Set", "유아 내의": "Baby Underwear", "바람막이 점퍼": "Windbreaker Jacket",
    "양말 세트": "Socks Set", "원피스": "Dress", "초등학생 책가방": "School Backpack", "필통": "Pencil Case",
    "스케치북 세트": "Sketchbook Set", "크레파스": "Crayons", "베이비 바디워시": "Baby Body Wash", "보습 크림": "Moisturizing Cream",
    "물티슈": "Wet Wipes", "기저귀": "Diapers", "소설": "Novel", "에세이": "Essay",
    "자기계발서": "Self-Help Book", "인문학 도서": "Humanities Book", "외국어 학습서": "Language Study Book", "LP 음반": "LP Record",
    "CD 앨범": "CD Album", "악보집": "Music Sheet Book", "블루레이 디스크": "Blu-ray Disc", "영화 DVD": "Movie DVD",
    "영화 굿즈": "Movie Merchandise", "콘솔 타이틀": "Console Game Title", "보드게임": "Board Game", "퍼즐 세트": "Puzzle Set",
    "만년필": "Fountain Pen", "다이어리": "Diary", "노트 패드": "Notepad", "스티커 팩": "Sticker Pack",
    "메모리폼 목베개": "Memory Foam Neck Pillow", "콘솔 트레이": "Console Tray", "스마트폰 거치대": "Smartphone Mount", "차량용 컵홀더": "Car Cup Holder",
    "가죽 세정제": "Leather Cleaner", "카샴푸": "Car Shampoo", "물왁스": "Liquid Wax", "휠 크리너": "Wheel Cleaner",
    "4K 2채널 블랙박스": "4K 2-Channel Dashcam", "Wi-Fi 지원 블랙박스": "Wi-Fi Dashcam", "무선 카플레이 어댑터": "Wireless CarPlay Adapter", "시가잭 충전기": "Car Charger",
    "HUD 헤드업 디스플레이": "HUD Head-Up Display", "배변 패드": "Pee Pads", "가죽 리드줄": "Leather Leash", "애견 하우스": "Dog House",
    "식기 매트": "Pet Bowl Mat", "고양이 모래": "Cat Litter", "스크래처": "Scratcher", "캣타워": "Cat Tree",
    "낚시 장난감": "Teaser Toy", "동결건조 사료": "Freeze-Dried Food", "그레인프리 사료": "Grain-Free Food", "수제 사료": "Homemade Food",
    "강아지 껌": "Dog Chew", "츄르": "Churu", "동결건조 닭가슴살": "Freeze-Dried Chicken Breast", "반려동물 인식표": "Pet ID Tag",
    "이동 가방": "Carrier Bag", "반려동물 의류": "Pet Clothing", "브러쉬": "Brush", "저자극 샴푸": "Mild Shampoo",
    "발톱 깎기": "Nail Clippers"
}

CATEGORY_ATTRIBUTES = {
    "electronics": {
        "use_cases": ["대학생용", "게이밍", "크리에이터용", "사무용", "휴대용", "전문가용", "비즈니스용", "가정용"],
        "feature_profiles": ["초경량", "고성능", "대용량", "스마트", "가성비", "슬림형", "고해상도", "저소음", "속도 빠른"],
        "brand_tiers": ["프리미엄", "하이엔드", "보급형", "실속형", "프로"],
        "style_tags": ["미니멀", "모던", "감성", "심플", "유니크"],
        "product_types": {
            "laptops": ["노트북", "울트라북", "태블릿 PC", "워크스테이션", "랩탑"],
            "smartphones": ["스마트폰", "휴대폰", "스마트 기기"],
            "earphones": ["무선 이어폰", "블루투스 이어폰", "헤드폰", "이어버드"],
            "tablets": ["태블릿", "패드", "드로잉 태블릿"],
            "smartwatches": ["스마트워치", "웨어러블 밴드", "피트니스 트래커"],
            "cameras": ["미러리스 카메라", "DSLR", "액션캠", "브이로그 카메라"],
            "monitors": ["게이밍 모니터", "와이드 모니터", "4K 모니터", "사무용 모니터"],
            "keyboards": ["기계식 키보드", "무소음 키보드", "블루투스 키보드"],
            "mice": ["무선 마우스", "버티컬 마우스", "게이밍 마우스"],
            "chargers": ["고속 충전기", "멀티 어댑터", "무선 충전 패드"]
        },
        "synonyms": {
            "laptops": ["랩탑", "컴퓨터", "맥북", "그램", "PC", "컴터", "과제용"],
            "smartphones": ["휴대폰", "핸드폰", "스마트폰", "폰", "아이폰", "갤럭시"],
            "earphones": ["블루투스 이어폰", "에어팟", "버즈", "헤드셋"],
            "tablets": ["아이패드", "갤럭시탭", "패드", "태블릿PC"]
        }
    },
    "fashion": {
        "use_cases": ["데일리용", "오피스룩", "캐주얼", "여행용", "피크닉용", "스트릿룩", "포멀"],
        "feature_profiles": ["경량", "통기성 좋은", "편안한", "트렌디한", "베이직", "고급스러운", "실용적인"],
        "brand_tiers": ["디자이너", "클래식", "실속형", "베이직", "프리미엄"],
        "style_tags": ["모던", "감성", "심플", "스포티", "유니크"],
        "product_types": {
            "mens_apparel": ["셔츠", "슬랙스", "자켓", "청바지", "맨투맨", "니트"],
            "womens_apparel": ["원피스", "블라우스", "스커트", "가디건", "자켓", "슬랙스"],
            "footwear": ["스니커즈", "로퍼", "구두", "샌들", "런닝화", "운동화"],
            "bags": ["백팩", "숄더백", "크로스백", "토트백", "메신저백"],
            "accessories": ["목걸이", "귀걸이", "팔찌", "반지", "키링"],
            "watches": ["가죽 시계", "메탈 시계", "드레스 워치"],
            "hats": ["볼캡", "버킷햇", "비니", "캡모자"],
            "scarves": ["머플러", "스카프", "쁘띠스카프"],
            "belts": ["가죽 벨트", "캐주얼 벨트", "자동 벨트"]
        },
        "synonyms": {
            "mens_apparel": ["남성 옷", "남성복", "남성의류"],
            "womens_apparel": ["여성 옷", "여성복", "여성의류"],
            "footwear": ["신발", "스니커즈", "운동화", "슈즈"],
            "bags": ["가방", "백", "배낭", "파우치"]
        }
    },
    "home_living": {
        "use_cases": ["사무용", "침실용", "서재용", "주방용", "거실용", "인테리어용", "원룸용"],
        "feature_profiles": ["미니멀", "친환경", "방수", "수납이 편리한", "튼튼한", "다용도", "공간절약형"],
        "brand_tiers": ["자연주의", "모던라이프", "실속형", "디자인가구", "프리미엄"],
        "style_tags": ["북유럽", "미니멀", "모던", "클래식", "내추럴"],
        "product_types": {
            "furniture": ["책상", "의자", "수납장", "소파", "침대 프레임", "식탁"],
            "lighting": ["무드등", "단스탠드", "장스탠드", "벽등", "데스크 스탠드"],
            "kitchenware": ["냄비", "프라이팬", "식기 세트", "칼블럭", "머그잔"],
            "bedding": ["토퍼", "이불 커버", "베개 세트", "차렵 이불"],
            "storage": ["리빙박스", "정리함", "옷걸이 행거", "서랍장"],
            "cleaning_supplies": ["밀대 청소기", "청소용 브러쉬", "휴지통", "물걸레"],
            "candles": ["디퓨저", "소이 캔들", "아로마 캔들", "캔들 워머"],
            "rugs": ["단색 러그", "발매트", "사이잘룩 러그", "거실 매트"]
        },
        "synonyms": {
            "furniture": ["가구", "책상", "의자", "테이블", "소파"],
            "bedding": ["침구", "이불", "베개", "침대용품"],
            "storage": ["수납", "정리", "옷장", "선반"]
        }
    },
    "beauty": {
        "use_cases": ["민감성용", "건성용", "지성용", "데일리", "선물용", "집중케어용", "여행용"],
        "feature_profiles": ["저자극", "수분충전", "진정효과", "미백", "주름개선", "비건", "올인원"],
        "brand_tiers": ["더마케어", "내추럴", "럭셔리", "에센셜", "데일리"],
        "style_tags": ["감성", "심플", "모던", "내추럴"],
        "product_types": {
            "skincare": ["토너", "세럼", "크림", "에센스", "마스크팩", "앰플", "클렌저"],
            "haircare": ["샴푸", "트리트먼트", "헤어에센스", "헤어팩"],
            "fragrance": ["오드퍼퓸", "드레스퍼퓸", "향수", "보디미스트"],
            "mens_grooming": ["올인원로션", "쉐이빙폼", "왁스", "폼클렌징"],
            "body_care": ["바디로션", "바디워시", "바디오일", "핸드크림"],
            "makeup": ["쿠션", "립밤", "아이섀도우", "파운데이션", "틴트"],
            "nail_care": ["네일팁", "네일세럼", "젤네일"]
        },
        "synonyms": {
            "skincare": ["화장품", "기초화장품", "피부관리", "세안제"],
            "makeup": ["화장품", "메이크업", "화장"]
        }
    },
    "sports_outdoors": {
        "use_cases": ["홈트용", "야외활동용", "피트니스용", "필라테스용", "캠핑용", "러닝용", "전문가용"],
        "feature_profiles": ["고탄성", "인체공학적", "휴대용", "충격흡수", "미끄럼방지", "경량", "내구성 좋은"],
        "brand_tiers": ["스포티", "프로페셔널", "엔트리", "액티브", "하이포퍼먼스"],
        "style_tags": ["스포티", "모던", "유니크", "내추럴"],
        "product_types": {
            "fitness_equipment": ["덤벨", "요가매트", "폼롤러", "실내자전거", "악력기", "푸쉬업바"],
            "outdoor_gear": ["캠핑 체어", "텐트", "타프", "랜턴", "등산스틱"],
            "cycling": ["헬멧", "자전거 라이트", "안장 가방", "사이클 장갑"],
            "swimming": ["물안경", "수영모", "귀마개", "수영가방"],
            "yoga_pilates": ["요가 링", "요가 삭스", "필라테스 루프 밴드"],
            "hiking": ["등산화", "등산 배낭", "무릎 보호대"],
            "team_sports": ["축구공", "농구공", "배드민턴 라켓", "셔틀콕"]
        },
        "synonyms": {
            "fitness_equipment": ["운동", "헬스", "홈트", "아령", "매트"],
            "outdoor_gear": ["캠핑", "아웃도어", "야외"]
        }
    },
    "food_grocery": {
        "use_cases": ["다이어트용", "아침대용", "간식용", "건강식", "캠핑용", "반찬용", "선물용"],
        "feature_profiles": ["무설탕", "저칼로리", "유기농", "고단백", "신선한", "천연성분", "간편한"],
        "brand_tiers": ["프레시", "유기농", "실속형", "웰빙", "프리미엄"],
        "style_tags": ["내추럴", "웰빙", "모던", "심플"],
        "product_types": {
            "health_foods": ["닭가슴살", "샐러드", "오트밀", "곤약밥"],
            "beverages": ["드립백 커피", "유기농 녹차", "탄산수", "콤부차", "두유"],
            "snacks": ["단백질 바", "통밀 크래커", "아몬드", "건조 과일칩"],
            "fresh_produce": ["방울토마토", "사과", "고구마", "미니단호박"],
            "condiments": ["올리브유", "저칼로리 드레싱", "스테비아", "히말라야 핑크솔트"],
            "supplements": ["유산균", "오메가3", "멀티비타민", "루테인"]
        },
        "synonyms": {
            "supplements": ["영양제", "비타민", "건강기능식품"],
            "beverages": ["음료", "커피", "차", "물", "음료수"]
        }
    },
    "baby_kids": {
        "use_cases": ["신생아용", "유아동용", "놀이용", "등교용", "출산선물용", "목욕용"],
        "feature_profiles": ["친환경", "안전검증 완료", "부드러운", "창의력 발달", "저자극", "경량"],
        "brand_tiers": ["세이프티", "에코", "키즈월드", "프리미엄"],
        "style_tags": ["큐트", "내추럴", "비비드", "심플"],
        "product_types": {
            "infant_products": ["젖병 소독기", "아기 침대", "유모차 라이너", "보행기"],
            "toys": ["원목 블록", "오감 발달 촉감책", "조립식 완구", "역할놀이 세트"],
            "childrens_apparel": ["유아 내의", "바람막이 점퍼", "양말 세트", "원피스"],
            "school_supplies": ["초등학생 책가방", "필통", "스케치북 세트", "크레파스"],
            "baby_care": ["베이비 바디워시", "보습 크림", "물티슈", "기저귀"]
        },
        "synonyms": {
            "toys": ["장난감", "인형", "교구", "완구"],
            "baby_care": ["유아용품", "베이비", "기저귀"]
        }
    },
    "books_media": {
        "use_cases": ["취미용", "학습용", "선물용", "힐링용", "콜렉터용", "어린이용"],
        "feature_profiles": ["베스트셀러", "평점 높은", "소장가치 있는", "일러스트 포함", "개정판"],
        "brand_tiers": ["스탠다드", "에센셜", "리미티드", "스페셜 에디션"],
        "style_tags": ["클래식", "모던", "감성", "레트로"],
        "product_types": {
            "books": ["소설", "에세이", "자기계발서", "인문학 도서", "외국어 학습서"],
            "music": ["LP 음반", "CD 앨범", "악보집"],
            "film": ["블루레이 디스크", "영화 DVD", "영화 굿즈"],
            "games": ["콘솔 타이틀", "보드게임", "퍼즐 세트"],
            "stationery": ["만년필", "다이어리", "노트 패드", "스티커 팩"]
        },
        "synonyms": {
            "books": ["책", "도서", "소설책", "교재"],
            "games": ["보드게임", "스위치게임", "플레이스테이션", "게임기"]
        }
    },
    "automotive": {
        "use_cases": ["세차용", "차량 내부용", "안전 운전용", "캠핑/차박용", "자가정비용"],
        "feature_profiles": ["고화질", "인체공학적", "간편설치", "발수코팅", "대용량", "내구성 좋은"],
        "brand_tiers": ["프로카", "에센셜", "세이프", "마스터", "프리미엄"],
        "style_tags": ["모던", "스포티", "심플", "블랙"],
        "product_types": {
            "car_accessories": ["메모리폼 목베개", "콘솔 트레이", "스마트폰 거치대", "차량용 컵홀더"],
            "car_care": ["가죽 세정제", "카샴푸", "물왁스", "휠 크리너"],
            "dash_cameras": ["4K 2채널 블랙박스", "Wi-Fi 지원 블랙박스"],
            "car_electronics": ["무선 카플레이 어댑터", "시가잭 충전기", "HUD 헤드업 디스플레이"]
        },
        "synonyms": {
            "dash_cameras": ["블박", "블랙박스", "dashcam"],
            "car_care": ["세차", "세차용품", "왁스"]
        }
    },
    "pet_supplies": {
        "use_cases": ["노령견용", "신생묘용", "훈련용", "데일리", "보양식", "장거리 이동용"],
        "feature_profiles": ["유기농", "저알레르기", "천연소재", "스트레스 완화", "무독성", "튼튼한"],
        "brand_tiers": ["에코펫", "해피테일", "내추럴", "프리미엄", "스탠다드"],
        "style_tags": ["큐트", "내추럴", "심플", "비비드"],
        "product_types": {
            "dog_supplies": ["배변 패드", "가죽 리드줄", "애견 하우스", "식기 매트"],
            "cat_supplies": ["고양이 모래", "스크래처", "캣타워", "낚시 장난감"],
            "pet_food": ["동결건조 사료", "그레인프리 사료", "수제 사료"],
            "treats": ["강아지 껌", "츄르", "동결건조 닭가슴살"],
            "pet_accessories": ["반려동물 인식표", "이동 가방", "반려동물 의류"],
            "pet_grooming": ["브러쉬", "저자극 샴푸", "발톱 깎기"]
        },
        "synonyms": {
            "dog_supplies": ["강아지", "애견", "개용품"],
            "cat_supplies": ["고양이", "반려묘", "묘용품"],
            "pet_food": ["개사료", "고양이사료", "사료", "펫푸드"]
        }
    }
}

ATTRIBUTE_SYNONYMS = {
    "초경량": ["가벼운", "가볍다", "가벼움", "휴대용", "휴대성", "경량"],
    "경량": ["가벼운", "가볍다", "가벼움", "휴대용", "휴대성", "경량"],
    "게이밍": ["게임용", "게임", "고사양", "고화질"],
    "사무용": ["작업용", "회사용", "업무용", "오피스"],
    "비즈니스용": ["업무용", "회사용", "작업용"],
    "가성비": ["가성비", "저렴한", "저렴", "싼", "합리적인", "실속형"],
    "실속형": ["가성비", "저렴한", "저렴", "합리적인", "실속형"],
    "고성능": ["고사양", "빠른", "최고 성능", "프로", "강력한"],
    "대학생용": ["대학생", "과제용", "인강용", "학생", "공부용"],
    "여행용": ["휴대용", "캠핑", "출장", "야외", "이동식"],
    "수분충전": ["수분", "보습", "촉촉한", "건조한"],
    "진정효과": ["진정", "민감성", "순한", "트러블"],
    "저자극": ["순한", "민감성", "저자극"],
    "무설탕": ["제로", "무가당", "다이어트"],
    "저칼로리": ["라이트", "다이어트", "가벼운"],
    "유기농": ["친환경", "오가닉", "천연"],
    "고단백": ["프로틴", "단백질", "헬스"],
    "신선한": ["싱싱한", "산지직송", "프레시"],
    "친환경": ["에코", "유기농", "천연"],
    "안전검증 완료": ["안전한", "무독성", "안심"],
    "베스트셀러": ["인기", "추천", "베스트"],
    "평점 높은": ["추천", "만족", "우수"],
    "소장가치 있는": ["한정판", "소장", "특별한"],
    "고화질": ["깨끗한", "선명한", "FHD", "4K"],
    "간편설치": ["쉬운 설치", "간단한"],
    "발수코팅": ["방수", "발수"],
    "저알레르기": ["알러지 케어", "순한"],
    "천연소재": ["유기농", "천연", "오가닉"],
    "스트레스 완화": ["릴렉스", "힐링", "편안한"]
}


def category_price(rng, category: str) -> int:
    lo, hi = CATEGORY_PRICE_RANGES.get(category, (5_000, 1_500_000))
    raw = rng.uniform(lo, hi)
    return int(round(raw / 1_000) * 1_000)


def one_decimal_uniform_rating(rng: np.random.Generator) -> float:
    return float(np.round(rng.uniform(3.5, 5.0), 1))


def sample_long_tail_review_counts(rng: np.random.Generator, count: int) -> list[int]:
    pareto_samples = rng.pareto(a=1.55, size=count)
    review_counts = 10 + np.rint(pareto_samples * 28).astype(int)
    review_counts = np.clip(review_counts, 10, 5000)
    return review_counts.astype(int).tolist()


def biased_purchase_history(
    rng: np.random.Generator,
    products: list[dict[str, Any]],
    preference_style: str,
) -> list[str]:
    history_size = int(rng.integers(3, 21))
    weights = np.array(
        [0.75 if product["style_type"] == preference_style else 0.25 for product in products],
        dtype=float,
    )
    probabilities = weights / weights.sum()
    selected_indexes = rng.choice(
        len(products),
        size=history_size,
        replace=False,
        p=probabilities,
    )
    return [products[index]["product_id"] for index in selected_indexes]


def simulate_session_behavior(rng, psychographic_type: str) -> dict:
    params = PSYCHOGRAPHIC_SESSION_PARAMS[psychographic_type]
    page_visits = int(rng.integers(*params["page_visits_range"]))
    dwell_times = rng.uniform(*params["dwell_range"], size=page_visits)
    scroll_depths = rng.uniform(*params["scroll_range"], size=page_visits)
    query_reformulations = int(rng.integers(*params["query_ref_range"]))

    dwell_time_variance = float(np.var(dwell_times))
    average_scroll_depth = float(np.mean(scroll_depths))

    ctr_base = params["ctr_base"]
    ctr_noise = rng.normal(0.0, 0.04)
    ctr = float(np.clip(ctr_base + ctr_noise, 0.0, 1.0))

    N_norm = min(page_visits / 50, 1.0)
    sigma2_norm = min(dwell_time_variance / 10000, 1.0)
    SR_inv = 1.0 - average_scroll_depth
    Q_norm = min(query_reformulations / 10, 1.0)

    B_behavioral = (
        0.25 * N_norm
        + 0.25 * sigma2_norm
        + 0.20 * (1 - ctr)
        + 0.15 * SR_inv
        + 0.15 * Q_norm
    )
    brainfry_score = round(min(0.7 * B_behavioral, 1.0), 4)

    return {
        "page_visits": page_visits,
        "dwell_times": [float(round(v, 2)) for v in dwell_times],
        "dwell_time_variance": round(dwell_time_variance, 2),
        "scroll_depths": [float(round(v, 3)) for v in scroll_depths],
        "average_scroll_depth": round(average_scroll_depth, 3),
        "query_reformulations": query_reformulations,
        "ctr": round(ctr, 4),
        "brainfry_score": brainfry_score,
    }


def build_products(rng) -> list:
    total_subitems = sum(len(v) for v in CATEGORY_ITEMS.values())
    base = PRODUCT_COUNT // total_subitems
    remainder = PRODUCT_COUNT % total_subitems

    review_counts = sample_long_tail_review_counts(rng, PRODUCT_COUNT)
    products = []
    product_index = 0
    subitem_index = 0

    model_suffixes = ["Pro", "Air", "Lite", "Plus", "Max", "Prime", "Elite", "One", "Classic", "Smart"]
    model_codes = ["X", "Z", "V", "S", "K", "N", "M"]

    for category, subitems in CATEGORY_ITEMS.items():
        cat_ko = CATEGORY_MAP.get(category, category)
        cat_attrs = CATEGORY_ATTRIBUTES.get(category, {})

        for subitem in subitems:
            subitem_ko = SUBCATEGORY_MAP.get(subitem, subitem)
            count = base + (1 if subitem_index < remainder else 0)
            subitem_index += 1

            use_cases = cat_attrs.get("use_cases", ["기본형"])
            features = cat_attrs.get("feature_profiles", ["일반형"])
            brands = cat_attrs.get("brand_tiers", ["스탠다드"])
            styles = cat_attrs.get("style_tags", ["모던"])
            types = cat_attrs.get("product_types", {}).get(subitem, [subitem_ko])
            sub_synonyms = cat_attrs.get("synonyms", {}).get(subitem, [])

            for _ in range(count):
                product_index += 1
                price = category_price(rng, category)

                if price >= 1_000_000:
                    brand_tier_class = "premium"
                elif price >= 300_000:
                    brand_tier_class = "mid"
                else:
                    brand_tier_class = "budget"

                use_case = rng.choice(use_cases)
                feature = rng.choice(features)
                brand_tier = rng.choice(brands)
                style_tag = rng.choice(styles)
                product_type = rng.choice(types)

                suffix = f"{rng.choice(model_suffixes)} {rng.choice(model_codes)}{product_index % 100}"
                
                template_idx = product_index % 4
                if template_idx == 0:
                    title_ko = f"{feature} {use_case} {product_type} {suffix}"
                elif template_idx == 1:
                    title_ko = f"{style_tag} 스타일 {feature} {product_type} {suffix}"
                elif template_idx == 2:
                    title_ko = f"{brand_tier} {feature} {use_case} {product_type} {suffix}"
                else:
                    title_ko = f"{use_case} 추천 {feature} {product_type} {suffix}"

                use_case_en = TRANSLATIONS.get(use_case, use_case)
                feature_en = TRANSLATIONS.get(feature, feature)
                brand_en = TRANSLATIONS.get(brand_tier, brand_tier)
                style_en = TRANSLATIONS.get(style_tag, style_tag)
                type_en = TRANSLATIONS.get(product_type, product_type)

                if template_idx == 0:
                    title_en = f"{feature_en} {type_en} for {use_case_en} {suffix}"
                elif template_idx == 1:
                    title_en = f"{style_en} Style {feature_en} {type_en} {suffix}"
                elif template_idx == 2:
                    title_en = f"{brand_en} {feature_en} {type_en} for {use_case_en} {suffix}"
                else:
                    title_en = f"{feature_en} {type_en} Recommended for {use_case_en} {suffix}"

                description_ko = f"[{brand_tier}] {style_tag} 스타일의 {feature} {use_case} {product_type}입니다. 높은 성능과 뛰어난 디자인으로 큰 만족감을 줍니다."
                description_en = f"This is a {style_en.lower()} style {feature_en.lower()} {type_en.lower()} designed for {use_case_en.lower()} from our {brand_en} line."

                keywords_ko = [cat_ko, subitem_ko, product_type, use_case, feature, brand_tier, style_tag]
                feature_synonyms = ATTRIBUTE_SYNONYMS.get(feature, [])
                use_case_synonyms = ATTRIBUTE_SYNONYMS.get(use_case, [])
                keywords_ko.extend(feature_synonyms)
                keywords_ko.extend(use_case_synonyms)
                keywords_ko = list(set([k for k in keywords_ko if k]))

                synonyms_ko = [subitem_ko] + sub_synonyms
                synonyms_ko = list(set([s for s in synonyms_ko if s]))

                sentiment_score = float(round(rng.beta(5, 2), 2))
                stock_status = bool(rng.random() < 0.95)

                reviews_ko = [
                    f"정말 마음에 들어요. {product_type} 추천합니다!",
                    f"가격 대비 만족스럽습니다. 무난한 {product_type}네요.",
                    f"품질이 아주 훌륭합니다. {product_type} 대만족!",
                    f"생각보다 괜찮아요. 만족스러운 제품입니다.",
                    f"제가 산 {product_type} 중 최고입니다. 매우 만족스럽습니다.",
                ]
                review_text = str(rng.choice(reviews_ko))

                products.append({
                    "product_id": f"P{product_index:05d}",
                    "category": cat_ko,
                    "subcategory": subitem_ko,
                    "name": title_ko,
                    "price": price,
                    "brand": brand_tier_class,
                    "style_type": str(rng.choice(["utilitarian", "hedonic"], p=[0.5, 0.5])),
                    "star_rating": one_decimal_uniform_rating(rng),
                    "review_count": review_counts[product_index - 1],
                    "review_text": review_text,
                    "sentiment_score": sentiment_score,
                    "stock_status": stock_status,
                    "description": description_ko,
                    
                    # Bilingual metadata
                    "category_en": category,
                    "category_ko": cat_ko,
                    "subcategory_en": subitem,
                    "subcategory_ko": subitem_ko,
                    "title_en": title_en,
                    "title_ko": title_ko,
                    "keywords_ko": keywords_ko,
                    "synonyms_ko": synonyms_ko,
                })

    rng.shuffle(products)
    return products


def build_consumers(rng, products: list) -> list:
    consumers = []
    consumer_index = 0

    for type_idx, psychographic_type in enumerate(PSYCHOGRAPHIC_TYPES):
        count = PSYCHOGRAPHIC_COUNTS[type_idx]
        for _ in range(count):
            consumer_index += 1

            if psychographic_type == "hedonic":
                preference_style = "hedonic"
            elif psychographic_type == "utilitarian":
                preference_style = "utilitarian"
            else:
                preference_style = str(rng.choice(["utilitarian", "hedonic"]))

            session_behavior = simulate_session_behavior(rng, psychographic_type)

            consumers.append({
                "consumer_id": f"C{consumer_index:04d}",
                "psychographic_type": psychographic_type,
                "preference_style": preference_style,
                "budget_level": str(rng.choice(["low", "mid", "high"], p=[1/3, 1/3, 1/3])),
                "purchase_history": biased_purchase_history(rng, products, preference_style),
                "session_behavior": session_behavior,
                "ctr": session_behavior["ctr"],
                "brainfry_score": session_behavior["brainfry_score"],
            })

    return consumers


def write_json(path: Path, data: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)
    output_dir = Path(__file__).resolve().parent

    products = build_products(rng)
    consumers = build_consumers(rng, products)

    write_json(output_dir / "products.json", products)
    write_json(output_dir / "consumers.json", consumers)

    print(f"Generated {len(products)} products -> products.json")
    print(f"Generated {len(consumers)} consumers -> consumers.json")


if __name__ == "__main__":
    main()
