from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)
import anthropic
import json

PERSONA_PROMPTS = {
    "maximizer": """당신은 완벽주의적 온라인 쇼퍼입니다.
항상 최고의 선택을 찾으려 하고 모든 옵션을 꼼꼼히 비교합니다.
평가 기준: 상세 스펙 제공 여부(40%), 리뷰 신뢰도(30%), 선택지 다양성(30%)""",

    "value_seeker": """당신은 가성비를 최우선으로 생각하는 쇼퍼입니다.
같은 품질이라면 무조건 저렴한 쪽을 선택합니다.
평가 기준: 가격 대비 품질(50%), 할인 및 혜택 여부(30%), 예산 준수(20%)""",

    "loss_averse": """당신은 후회를 극도로 피하려는 쇼퍼입니다.
검증된 제품, 높은 리뷰 수, 베스트셀러를 선호합니다.
평가 기준: 사회적 증거 즉 리뷰 수와 베스트셀러 여부(50%), 평점(30%), 반품 용이성(20%)""",

    "impulsive": """당신은 즉각적인 결정을 선호하는 충동적 쇼퍼입니다.
너무 많은 선택지는 오히려 불편합니다.
평가 기준: 추천 간결성(40%), 결정 용이성(40%), 시각적 매력(20%)""",

    "hedonic": """당신은 쇼핑 자체를 즐기는 감성 소비자입니다.
디자인, 브랜드 이미지, 감성적 가치를 중시합니다.
평가 기준: 미적 품질 및 디자인(40%), 브랜드 스토리(30%), 감성적 만족(30%)""",

    "utilitarian": """당신은 기능과 효율을 중시하는 실용적 쇼퍼입니다.
필요한 기능이 있는지, 내구성이 좋은지를 봅니다.
평가 기준: 기능 충족도(40%), 내구성 및 품질(35%), 효율성(25%)""",
}

EVALUATION_TEMPLATE = """
당신의 페르소나:
{persona_description}

추천된 상품 목록:
{products_json}

소비자 상황:
- 검색어: {query}
- 예산: {budget}원
- BrainFry 수준: {brainfry_level}
- 추천 개수: {n_rec}개

위 추천 결과를 당신의 페르소나 기준으로 평가하라.

반드시 아래 JSON 형식으로만 응답하라. 다른 텍스트 없이 JSON만 출력:
{{
  "persona_satisfaction_score": <1.0에서 5.0 사이 소수점 1자리>,
  "decision_ease_score": <1.0에서 5.0 사이 소수점 1자리>,
  "reasoning": "<50자 이내 한 줄 평가>"
}}
"""


class PersonaEvaluator:
    def __init__(self):
        self.client = anthropic.Anthropic()

    def evaluate(self, persona_type: str, recommendations: list, plan_context: dict) -> dict:
        prompt = EVALUATION_TEMPLATE.format(
            persona_description=PERSONA_PROMPTS[persona_type],
            products_json=json.dumps(recommendations, ensure_ascii=False, indent=2),
            query=plan_context.get("query", ""),
            budget=plan_context.get("budget_ceiling", 0),
            brainfry_level=plan_context.get("brainfry_level", "LOW"),
            n_rec=plan_context.get("n_rec", 5),
        )
        response = self.client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        try:
            clean = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(clean)
        except json.JSONDecodeError:
            return {
                "persona_satisfaction_score": 3.0,
                "decision_ease_score": 3.0,
                "reasoning": "파싱 실패",
            }

    def evaluate_all(self, recommendations: list, plan_context: dict) -> dict:
        results = {}
        for ptype in PERSONA_PROMPTS:
            results[ptype] = self.evaluate(ptype, recommendations, plan_context)
        return results
