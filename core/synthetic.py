"""합성(가상) 데이터 — 실제 개인정보·기업정보를 쓰지 않는다.

- PERSONAS : 국민취업지원제도·청년도전지원사업 참여 이력과 고용보험 이력을 가진 가상 구직자
- POSTINGS : 고용24 채용정보와 같은 항목을 가진 가상 공고 (고용24 OpenAPI 승인 전 시연용)
- applicants_for() : 기업 화면에 보일 가상 지원자

참여 이력·고용보험 이력은 실제 서비스에서는 본인 동의 후 고용24에서 불러오는 비공개 정보다.
"""

PERSONAS = [
    {"id": "P-01", "alias": "김하늘", "age": 27, "label": "국민취업지원제도 참여 · 훈련 수료",
     "programs": [{"type": "국민취업지원제도", "track": "I유형", "qualified": "2026-04-20", "iap": "2026-05-02", "status": "참여 중"}],
     "activities": [
         {"kind": "상담", "name": "진로·직업상담 5회 (취업활동계획 수립)", "done": "2026-05-02"},
         {"kind": "훈련", "name": "웹 프론트엔드 개발자 양성과정 (HTML·CSS·JavaScript·React)", "hours": 480, "done": "2026-09-12"},
         {"kind": "프로젝트", "name": "팀 프로젝트: 지역 축제 안내 웹앱 (화면 설계·React 구현 담당)", "done": "2026-09-05"},
     ],
     "insurance": [{"company": "카페(아르바이트)", "acquired": "2024-03-02", "lost": "2024-12-31"}],
     "desire": {"job": "웹 개발", "region": "서울"}},
    {"id": "P-02", "alias": "이서준", "age": 24, "label": "청년도전지원사업 수료",
     "programs": [{"type": "청년도전지원사업", "track": "장기 프로그램", "started": "2026-04-01", "completed": "2026-08-29", "status": "수료"}],
     "activities": [
         {"kind": "프로그램", "name": "자신감 회복·진로 탐색 프로그램", "done": "2026-05-30"},
         {"kind": "직무체험", "name": "물류센터 사무 보조 직무체험 4주 (입출고 대장 정리·재고 확인)", "done": "2026-07-25"},
         {"kind": "훈련", "name": "엑셀 실무 기초 (함수·피벗 테이블)", "hours": 40, "done": "2026-08-14"},
     ],
     "insurance": [],
     "desire": {"job": "사무·물류 관리", "region": "경기"}},
    {"id": "P-03", "alias": "박지민", "age": 29, "label": "국민취업지원제도 참여 · 참여 중 취업 이력 있음",
     "programs": [{"type": "국민취업지원제도", "track": "II유형", "qualified": "2026-02-24", "iap": "2026-03-10", "status": "참여 중"}],
     "activities": [
         {"kind": "훈련", "name": "품질관리 실무 (QC 7가지 도구·측정기 사용)", "hours": 160, "done": "2026-06-19"},
         {"kind": "자격", "name": "품질경영산업기사 필기 합격", "done": "2026-06-05"},
     ],
     "insurance": [{"company": "○○전자(계약직)", "acquired": "2026-07-01", "lost": "2026-08-31"}],
     "desire": {"job": "생산·품질관리", "region": "무관"}},
    {"id": "P-04", "alias": "최유나", "age": 26, "label": "일반 직업훈련만 수료",
     "programs": [],
     "activities": [
         {"kind": "훈련", "name": "UI/UX 디자인 과정 (Figma·사용자 조사·프로토타입)", "hours": 320, "done": "2026-08-21"},
         {"kind": "프로젝트", "name": "포트폴리오: 동네 병원 예약 앱 리디자인", "done": "2026-08-20"},
     ],
     "insurance": [],
     "desire": {"job": "디자인", "region": "서울"}},
]

# 공고 항목은 고용24 채용정보(공고명·직종·근무지역·고용형태·임금·마감일)와 맞추고,
# 공고 점검에 필요한 기업 정보(피보험자 수·우선지원대상 여부·체불 명단 여부)를 덧붙였다.
POSTINGS = [
    {"id": "JOB-01", "company": "한빛소프트랩", "region": "서울 마포구", "title": "웹 프론트엔드 개발자 (신입)", "job": "웹 개발",
     "emp_type": "정규직", "wage": 2800000, "weekly_hours": 40, "insured": 18, "priority": True, "arrears": False,
     "skills": ["JavaScript", "React", "HTML", "CSS", "웹"], "close": "2026-10-31"},
    {"id": "JOB-02", "company": "누리커머스", "region": "서울 금천구", "title": "쇼핑몰 웹 퍼블리셔", "job": "웹 개발",
     "emp_type": "정규직", "wage": 2400000, "weekly_hours": 40, "insured": 9, "priority": True, "arrears": False,
     "skills": ["HTML", "CSS", "웹", "퍼블리싱"], "close": "2026-11-07"},
    {"id": "JOB-03", "company": "다온물류", "region": "경기 이천시", "title": "물류 사무원 (입출고 관리)", "job": "사무·물류",
     "emp_type": "정규직", "wage": 2300000, "weekly_hours": 40, "insured": 42, "priority": True, "arrears": False,
     "skills": ["엑셀", "사무", "물류", "재고", "입출고"], "close": "2026-10-28"},
    {"id": "JOB-04", "company": "세진정밀", "region": "인천 남동구", "title": "품질관리 사원", "job": "생산·품질",
     "emp_type": "정규직", "wage": 2600000, "weekly_hours": 40, "insured": 65, "priority": True, "arrears": False,
     "skills": ["품질", "QC", "측정", "생산"], "close": "2026-11-14"},
    {"id": "JOB-05", "company": "한결전자", "region": "경북 구미시", "title": "품질검사원 (주간)", "job": "생산·품질",
     "emp_type": "정규직", "wage": 2500000, "weekly_hours": 40, "insured": 120, "priority": True, "arrears": False,
     "skills": ["품질", "검사", "측정", "생산"], "close": "2026-11-20"},
    {"id": "JOB-06", "company": "온새미디자인", "region": "대구 북구", "title": "UI 디자이너 (신입)", "job": "디자인",
     "emp_type": "정규직", "wage": 2400000, "weekly_hours": 40, "insured": 7, "priority": True, "arrears": False,
     "skills": ["UI", "UX", "Figma", "디자인", "프로토타입"], "close": "2026-11-05"},
    {"id": "JOB-07", "company": "브릿지랩", "region": "서울 강남구", "title": "UX 디자이너 (계약직 12개월)", "job": "디자인",
     "emp_type": "계약직", "wage": 2700000, "weekly_hours": 40, "insured": 25, "priority": True, "arrears": False,
     "skills": ["UX", "Figma", "디자인", "사용자 조사"], "close": "2026-10-30"},
    {"id": "JOB-08", "company": "코드온", "region": "경기 성남시", "title": "주니어 웹 개발자", "job": "웹 개발",
     "emp_type": "정규직", "wage": 2600000, "weekly_hours": 40, "insured": 3, "priority": True, "arrears": False,
     "skills": ["JavaScript", "웹", "개발"], "close": "2026-11-10"},
    {"id": "JOB-09", "company": "가온유통", "region": "서울 구로구", "title": "사무 보조 (재고 관리)", "job": "사무·물류",
     "emp_type": "정규직", "wage": 2000000, "weekly_hours": 40, "insured": 30, "priority": True, "arrears": False,
     "skills": ["사무", "엑셀", "재고"], "close": "2026-11-03"},
    {"id": "JOB-10", "company": "대명산업", "region": "경기 화성시", "title": "생산·품질 사원", "job": "생산·품질",
     "emp_type": "정규직", "wage": 2500000, "weekly_hours": 40, "insured": 50, "priority": True, "arrears": True,
     "skills": ["생산", "품질", "측정"], "close": "2026-11-12"},
    {"id": "JOB-11", "company": "바다로지스", "region": "부산 강서구", "title": "물류 관리 사원", "job": "사무·물류",
     "emp_type": "정규직", "wage": 2450000, "weekly_hours": 40, "insured": 35, "priority": True, "arrears": False,
     "skills": ["물류", "재고", "엑셀", "사무"], "close": "2026-11-18"},
    {"id": "JOB-12", "company": "대한금융서비스", "region": "서울 영등포구", "title": "웹 서비스 개발자", "job": "웹 개발",
     "emp_type": "정규직", "wage": 3500000, "weekly_hours": 40, "insured": 800, "priority": False, "arrears": False,
     "skills": ["JavaScript", "웹", "개발", "React"], "close": "2026-11-15"},
]
for _p in POSTINGS:
    _p["source"] = "synthetic"
    _p["company"] += " (가상)"
    _p["url"] = ""

# 기업 화면용 가상 지원자. 지원자마다 동의 여부와 (비공개) 참여 이력이 다르다.
_APPLICANT_TEMPLATES = [
    {"suffix": "A", "age": 25, "consent": True, "headline": "{job} 직무 관련 훈련 수료, 실습 프로젝트에서 실무 도구 사용 경험",
     "points": ["{job} 직무 훈련 과정 수료", "실습 프로젝트에서 실무 도구 사용", "팀 과제 일정 관리 담당"],
     "programs": [{"type": "청년도전지원사업", "completed": "2026-07-31", "status": "수료"}], "insurance": []},
    {"suffix": "B", "age": 31, "consent": True, "headline": "{job} 분야 아르바이트 1년, 고객 응대·문서 정리 경험",
     "points": ["{job} 분야 아르바이트 1년", "고객 응대·문서 정리"],
     "programs": [], "insurance": [{"company": "△△마트", "acquired": "2025-01-02", "lost": "2025-12-31"}]},
    {"suffix": "C", "age": 28, "consent": False, "headline": "{job} 직무 전환 준비, 관련 온라인 강의 수료",
     "points": ["{job} 관련 온라인 강의 수료", "이전 직무에서 일정·재고 관리"],
     "programs": [{"type": "국민취업지원제도", "qualified": "2026-03-02", "iap": "2026-03-16", "status": "참여 중"}], "insurance": []},
]
_APPLIED = ["2026-10-02", "2026-10-05", "2026-10-07"]


def applicants_for(posting: dict) -> list[dict]:
    out = []
    for i, t in enumerate(_APPLICANT_TEMPLATES):
        out.append({"id": f"{posting['id']}-{t['suffix']}", "alias": f"지원자 {t['suffix']}", "age": t["age"], "consent": t["consent"],
                    "headline": t["headline"].format(job=posting["job"]), "programs": t["programs"], "insurance": t["insurance"],
                    "points": [x.format(job=posting["job"]) for x in t["points"]], "portfolio": "",
                    "applied": _APPLIED[i]})
    return out


def persona(pid: str) -> dict | None:
    return next((p for p in PERSONAS if p["id"] == pid), None)


def posting(jid: str) -> dict | None:
    return next((p for p in POSTINGS if p["id"] == jid), None)
