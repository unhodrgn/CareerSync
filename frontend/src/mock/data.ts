// Demo data for screens whose backend is not built yet (CV analysis, scoring, recommendation).
// Replace each export with an API call when the matching endpoint lands.

export interface MockCriterion {
  id: number;
  name: string;
  description: string;
  weight: number;
}

export interface MockApplicant {
  id: number;
  name: string;
  email: string;
  years: number;
  location: string;
  status: "검토 전" | "서류 검토" | "면접 예정" | "보류";
  // per-criterion score (0-100) and evidence, keyed by criterion id
  scores: Record<number, { score: number; evidence: string }>;
  summary: string;
}

export const MOCK_JOB_TITLE = "백엔드 개발자 (Java/Spring)";

export const MOCK_CRITERIA: MockCriterion[] = [
  { id: 1, name: "Java", description: "백엔드 개발 경험", weight: 30 },
  { id: 2, name: "Spring", description: "Spring 프레임워크 경험", weight: 25 },
  { id: 3, name: "DB", description: "데이터베이스 설계/활용 경험", weight: 20 },
  { id: 4, name: "프로젝트 경험", description: "관련 프로젝트 경험", weight: 15 },
  { id: 5, name: "문제 해결 능력", description: "기술 문제 해결 능력", weight: 10 },
];

export const MOCK_APPLICANTS: MockApplicant[] = [
  {
    id: 101,
    name: "김지원",
    email: "kimjiwon@example.com",
    years: 3,
    location: "서울",
    status: "서류 검토",
    scores: {
      1: { score: 90, evidence: "3년 이상 실무 경험, 프로젝트 다수" },
      2: { score: 85, evidence: "Spring Boot 기반 프로젝트 경험" },
      3: { score: 80, evidence: "MySQL, PostgreSQL 활용 경험 보유" },
      4: { score: 85, evidence: "대규모 서비스 개발 경험 보유" },
      5: { score: 75, evidence: "알고리즘 및 장애 해결 경험" },
    },
    summary:
      "지원자는 당사에서 요구하는 Java 및 Spring 기반 백엔드 역량을 대부분 충족하고 있으며, 프로젝트 경험과 문제 해결 능력이 우수하여 해당 포지션에 적합한 지원자로 판단됩니다.",
  },
  {
    id: 102,
    name: "이서준",
    email: "seojun.lee@example.com",
    years: 4,
    location: "경기",
    status: "검토 전",
    scores: {
      1: { score: 80, evidence: "Java 8~17 기반 API 서버 4년 운영" },
      2: { score: 70, evidence: "Spring MVC 경험, Spring Boot 경험은 짧음" },
      3: { score: 90, evidence: "Oracle·PostgreSQL 튜닝, 인덱스 설계 경험" },
      4: { score: 70, evidence: "사내 시스템 위주 프로젝트" },
      5: { score: 80, evidence: "배치 장애 원인 분석·개선 사례" },
    },
    summary:
      "데이터베이스 역량이 특히 뛰어나며 Java 실무 경험이 충분합니다. Spring Boot 기반 신규 서비스 경험은 면접에서 확인이 필요합니다.",
  },
  {
    id: 103,
    name: "박하은",
    email: "haeun.park@example.com",
    years: 0,
    location: "서울",
    status: "검토 전",
    scores: {
      1: { score: 65, evidence: "학부 과제 및 부트캠프 Java 프로젝트" },
      2: { score: 60, evidence: "Spring Boot 토이 프로젝트 1건" },
      3: { score: 55, evidence: "MySQL 기본 CRUD 수준" },
      4: { score: 75, evidence: "팀 프로젝트 3건, 배포 경험 있음" },
      5: { score: 70, evidence: "알고리즘 문제 풀이 꾸준히 수행" },
    },
    summary:
      "신입 지원자로 기본기는 갖추었으나 실무 경험이 부족합니다. 성장 가능성과 프로젝트 주도 경험이 강점입니다.",
  },
];

/** Weighted fit score: sum(weight × score) / 100, computed at read time (README scoring rules). */
export function fitScore(applicant: MockApplicant, criteria: MockCriterion[] = MOCK_CRITERIA): number {
  const total = criteria.reduce((sum, c) => sum + c.weight, 0) || 1;
  const weighted = criteria.reduce((sum, c) => sum + c.weight * (applicant.scores[c.id]?.score ?? 0), 0);
  return Math.round(weighted / total);
}

/** Stable demo match percentage for a real job until the recommendation API exists. */
export function demoMatch(jobId: number): number {
  return 70 + ((jobId * 37) % 26);
}

export const MOCK_RESUME = {
  fileName: "김지원_이력서.pdf",
  analyzedAt: "2026-10-01",
  basic: {
    이름: "김지원",
    "희망 직무": "백엔드 개발자",
    경력: "3년",
    "희망 근무지": "서울",
    학력: "컴퓨터공학 학사",
  } as Record<string, string>,
  skills: [
    { name: "Python", years: 5, level: 90 },
    { name: "Django", years: 3, level: 70 },
    { name: "데이터 분석", years: 2, level: 50 },
    { name: "AWS", years: 2, level: 45 },
    { name: "프로젝트 경험", years: 4, level: 80 },
  ],
  summary:
    "지원자는 백엔드 개발 및 데이터 분석 경험이 풍부하며, 특히 Python과 Django를 활용한 웹 서비스 개발 경험이 돋보입니다. 클라우드 환경(AWS)에 대한 이해도도 높아 다양한 직무에 적합한 역량을 보유하고 있습니다.",
  masked: ["전화번호", "주소", "생년월일"],
};
