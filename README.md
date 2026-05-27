# CARA-agent

CARA(Context-Aware Recommendation Agent)는 사용자의 현재 탐색 행동, 대화 의도, 예산, 심리적 쇼핑 성향을 함께 반영해 상품을 추천하는 FastAPI 기반 멀티 에이전트 데모입니다.

현재 버전은 다음 흐름을 제공합니다.

- `CARA.html`: 사용자가 상품을 찾고 CARA와 대화하며 추천을 받는 쇼핑 화면
- `admin.html`: 세션, 에이전트 실행 로그, BrainFry 통계, 벤치마크 평가를 확인하는 관리자 화면
- `main.py`: 정적 화면, 상품 검색 도구, 추천 API, 관리자 API를 제공하는 FastAPI 서버
- `planner_agent.py`: 사용자 의도, BrainFry 상태, 예산, 선호 스타일을 정리하는 Planner Agent
- `conversation_agent.py`: 2턴 확인 대화와 텍스트 기반 인지 과부하 감지를 담당하는 Conversation Agent
- `executor_agent.py`: 상품 후보 검색 및 RAG 스타일 점수 기반 재정렬을 담당하는 Executor Agent
- `critic_agent.py`: 예산, 평점, 다양성, 추천 개수 규칙을 적용해 최종 결과를 검수하는 Critic Agent

## 주요 기능

- 상품 카탈로그 20,000개와 소비자 프로필 200개를 로컬 JSON 데이터로 로드
- 한국어/영어 검색어, 동의어, 가격 조건, 스타일 조건을 반영한 상품 검색
- 사용자 행동 지표 기반 BrainFry score 계산
- BrainFry score에 따른 추천 개수 자동 조절
- `utilitarian`, `hedonic`, `maximizer`, `value_seeker`, `loss_averse`, `impulsive` 성향 기반 추천 점수 보정
- 세션별 채팅 기록, 에이전트 실행 트레이스, 이벤트 로그를 SQLite에 저장
- 관리자 화면에서 세션 타임라인, BrainFry 분포, 페르소나 평가 확인
- CARA 추천과 인기순 baseline을 비교하는 벤치마크 실행 스크립트 포함

## 프로젝트 구조

| 파일 | 설명 |
| --- | --- |
| `main.py` | FastAPI 서버 진입점. 앱 화면, 상품 도구 API, 추천 API, 관리자 API를 제공 |
| `CARA.html` | 사용자용 CARA 추천 인터페이스 |
| `admin.html` | 관리자/실험 확인용 대시보드 |
| `planner_agent.py` | 사용자 컨텍스트를 추천 계획으로 변환 |
| `conversation_agent.py` | 2턴 대화, 텍스트 BrainFry 감지, API 키 로딩 |
| `executor_agent.py` | 상품 검색, fallback 후보 병합, RAG 점수 계산 |
| `critic_agent.py` | 최종 추천 검수 및 개수/예산/품질 조정 |
| `database.py` | SQLite 테이블과 DB 세션 설정 |
| `persona_evaluator.py` | 6개 쇼핑 페르소나 기준 추천 품질 평가 |
| `benchmark_runner.py` | 20개 시나리오로 CARA와 baseline 비교 |
| `generate_synthetic_dataset.py` | 상품/소비자 synthetic dataset 생성 |
| `generate_product_images.py` | 상품 이미지 PNG 생성 |
| `products.json` | 상품 카탈로그 20,000개 |
| `consumers.json` | 소비자 프로필 200명 |
| `benchmark_results.json` | 최근 벤치마크 결과 |
| `assets/products/` | 상품 이미지 파일 |

## 설치

Python 3.11 이상을 권장합니다.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

현재 코드에서는 FastAPI 서버와 SQLite ORM을 사용하므로, 환경에 `sqlalchemy`가 없다면 추가로 설치하세요.

```bash
pip install sqlalchemy
```

## 환경 변수

`.env.example`을 참고해 `.env` 파일을 만듭니다.

```env
ANTHROPIC_API_KEY=your_anthropic_api_key
OPENAI_API_KEY=your_openai_api_key
```

- `ANTHROPIC_API_KEY`: Conversation Agent와 Persona Evaluator에서 Claude 호출에 사용
- `OPENAI_API_KEY`: 검색어 정제와 텍스트 BrainFry 감지에 사용

키가 없어도 일부 rule-based fallback은 동작하지만, 대화 품질 평가와 LLM 기반 감지는 제한됩니다.

## 실행

서버를 실행합니다.

```bash
python main.py
```

브라우저에서 아래 주소를 엽니다.

- 사용자 화면: `http://127.0.0.1:8000/app`
- 직접 파일 경로: `http://127.0.0.1:8000/CARA.html`
- 관리자 화면: `http://127.0.0.1:8000/admin.html`
- API 상태 확인: `http://127.0.0.1:8000/`

서버는 기본적으로 `0.0.0.0:8000`에서 실행됩니다.

## 추천 플로우

1. 사용자가 상품명, 예산, 선호 표현을 입력합니다.
2. Planner Agent가 소비자 프로필, 세션 행동, 명시 조건을 바탕으로 계획을 만듭니다.
3. Conversation Agent가 필요한 경우 짧은 확인 대화를 진행하고, 텍스트 BrainFry 신호를 반영합니다.
4. Executor Agent가 상품 후보를 검색하고 RAG 점수로 재정렬합니다.
5. Critic Agent가 예산 초과, 낮은 평점, 스타일 다양성, 최소 추천 개수를 검수합니다.
6. 프론트엔드는 최종 추천 상품과 표시 힌트를 받아 화면에 렌더링합니다.

## 주요 API

| Method | Endpoint | 설명 |
| --- | --- | --- |
| `GET` | `/` | 서버 상태 확인 |
| `GET` | `/CARA.html` | 사용자 화면 제공 |
| `GET` | `/admin.html` | 관리자 화면 제공 |
| `GET` | `/app` | 사용자 화면 alias |
| `GET` | `/consumers/{consumer_id}/history` | 소비자 구매 이력, 세션 행동, preference vector 조회 |
| `GET` | `/products/search` | 키워드, 가격, 스타일, 카테고리 기반 상품 검색 |
| `GET` | `/products/trending` | 리뷰 수 기준 인기 상품 조회 |
| `GET` | `/products/price-distributions` | 카테고리별 가격 분포 조회 |
| `POST` | `/api/plan` | Planner Agent 실행 |
| `POST` | `/api/chat` | Conversation Agent 대화 턴 실행 |
| `POST` | `/api/recommend` | Planner, Executor, Critic 기반 최종 추천 생성 |
| `GET` | `/admin/sessions` | 최근 세션 목록 조회 |
| `GET` | `/admin/sessions/{session_id}` | 세션별 에이전트 타임라인과 채팅 기록 조회 |
| `GET` | `/admin/stats/brainfry` | BrainFry 분포 통계 조회 |
| `POST` | `/admin/benchmark/evaluate` | 단일 추천 요청에 대한 페르소나 평가 실행 |
| `GET` | `/admin/sessions/{session_id}/stream` | 세션 트레이스 SSE 스트림 |

## 데이터 스키마 요약

### Product

`products.json`의 상품은 다음 핵심 필드를 포함합니다.

- `product_id`: 상품 ID
- `category`, `subcategory`: 상품 카테고리
- `category_en`, `category_ko`, `subcategory_en`, `subcategory_ko`: 다국어 카테고리 메타데이터
- `name`, `title_en`, `title_ko`: 상품명
- `price`: 가격
- `brand`: 브랜드/가격대 라벨
- `style_type`: `utilitarian` 또는 `hedonic`
- `star_rating` 또는 `rating`: 평점
- `review_count`: 리뷰 수
- `review_text`, `sentiment_score`: 리뷰/감성 점수
- `keywords_ko`, `synonyms_ko`: 한국어 검색 보조 키워드
- `stock_status`: 재고 여부
- `description`: 상품 설명

### Consumer

`consumers.json`의 소비자 프로필은 다음 핵심 필드를 포함합니다.

- `consumer_id`: 소비자 ID
- `psychographic_type`: 쇼핑 성향
- `preference_style`: `utilitarian` 또는 `hedonic`
- `budget_level`: 예산 수준
- `purchase_history`: 구매한 상품 ID 목록
- `session_behavior`: 페이지 방문 수, 체류 시간 분산, 스크롤 깊이, CTR, BrainFry score 등

## BrainFry score

BrainFry는 사용자의 인지 과부하 상태를 나타내는 0.0~1.0 사이 점수입니다. 현재 코드는 행동 지표와 대화 텍스트, 자기보고 점수를 함께 사용합니다.

- 페이지 방문 수가 많을수록 증가
- 체류 시간 분산이 클수록 증가
- CTR이 낮을수록 증가
- 재검색/수정이 많을수록 증가
- 대화에서 피로, 혼란, 결정 회피 신호가 감지되면 증가

최종 추천 개수는 아래 방식으로 줄어듭니다.

```text
n_rec = max(1, round(7 * (1 - brainfry_score)))
```

즉, 인지 과부하가 높을수록 더 적고 단순한 추천을 제공합니다.

## 추천 점수와 검수

Executor Agent는 상품 텍스트 매칭, 카테고리 일치, 스타일 일치, 가격 근접도, 평점, 감성 점수, 페르소나별 가중치를 종합해 후보를 정렬합니다.

Critic Agent는 최종 반환 전에 아래 규칙을 적용합니다.

- 예산을 초과한 상품 제거
- 모든 상품 스타일이 동일하면 반대 스타일 후보를 일부 보강
- 낮은 평점 상품 제거
- 후보가 너무 적으면 예산을 단계적으로 완화해 복구
- `impulsive` 성향이면서 BrainFry가 높으면 단일 추천 중심으로 축소

## 벤치마크 실행

서버를 먼저 실행한 뒤 별도 터미널에서 실행합니다.

```bash
python benchmark_runner.py
```

벤치마크는 20개 시나리오를 대상으로 CARA와 인기순 baseline을 비교하고 `benchmark_results.json`을 갱신합니다.

확인 지표:

- 평균 만족도
- Hit@N
- 예산 준수율
- 선호 스타일 정렬도
- BrainFry 감소 추정치
- 페르소나별 만족도와 결정 용이성

## 데이터와 이미지 재생성

상품/소비자 데이터를 다시 생성합니다.

```bash
python generate_synthetic_dataset.py
```

상품 이미지를 다시 생성합니다.

```bash
python generate_product_images.py
```

이미지는 `assets/products/{product_id}.png` 경로에 저장됩니다.

## 개발 참고

- 서버 실행 시 `products.json`, `consumers.json`을 메모리에 로드합니다.
- 세션 로그는 `cara_sessions.db` SQLite 파일에 저장됩니다.
- `cara.db`, `cara_sessions.db`, `.env`는 로컬 실행 산출물로 취급하는 것이 좋습니다.
- 에이전트 단독 예시는 각 파일의 `main()`에서 실행할 수 있지만, 대부분 FastAPI 서버가 켜져 있어야 정상 동작합니다.
